"""G3.3: slide T branches along an unchanged collinear rail."""

import math
from collections import defaultdict
from itertools import combinations
from time import perf_counter

from check_connected import check_net_connectivity
from check_drc import point_to_pad_distance
from geometry_utils import point_to_segment_distance
from kicad_parser import Segment
from net_queries import calculate_route_length
from obstacle_cache import (add_net_obstacles_from_cache,
                            precompute_net_obstacles,
                            remove_net_obstacles_from_cache)
from routing_utils import pos_key

from .algorithm import (_connectivity_worse, _remove_result_custody,
                        _candidate_clears, _candidate_segments,
                        _sliding_candidate_families,
                        _touches_other_same_net)
from .changes import GlossChanges
from .pad_terminals import _new_boundary_right_angle, _pad_on_layer
from .via_mobile import _DIRECTIONS, _line_intersection, _other_end


def _vector_from(node, segment):
    other = _other_end(segment, pos_key(*node))
    return other[0] - node[0], other[1] - node[1]


def _opposite_collinear(node, first, second):
    if first.layer != second.layer:
        return False
    a = _vector_from(node, first)
    b = _vector_from(node, second)
    scale = max(1.0, math.hypot(*a) * math.hypot(*b))
    return (abs(a[0] * b[1] - a[1] * b[0]) <= 1e-8 * scale and
            a[0] * b[0] + a[1] * b[1] < -1e-9)


def _on_segment(point, segment):
    return (point_to_segment_distance(
                point[0], point[1], segment.start_x, segment.start_y,
                segment.end_x, segment.end_y) <= 1e-7 and
            min(segment.start_x, segment.end_x) - 1e-7 <= point[0] <=
            max(segment.start_x, segment.end_x) + 1e-7 and
            min(segment.start_y, segment.end_y) - 1e-7 <= point[1] <=
            max(segment.start_y, segment.end_y) + 1e-7)


def _slide_positions(node, anchor, rails):
    """Finite intersections of the rail and KRT's four line directions."""
    rail_vector = _vector_from(node, rails[0])
    positions = {}
    for direction in _DIRECTIONS:
        point = _line_intersection(node, rail_vector, anchor, direction)
        if point is None:
            continue
        point = round(point[0], 6), round(point[1], 6)
        if pos_key(*point) == pos_key(*node):
            continue
        if any(_on_segment(point, rail) for rail in rails):
            positions[pos_key(*point)] = point
    return positions.values()


def _node_is_fixed(pcb_data, net_id, layer, node, incident):
    if any(getattr(segment, "locked", False) for segment in incident):
        return True
    if any(pos_key(via.x, via.y) == pos_key(*node)
           for via in pcb_data.vias if via.net_id == net_id):
        return True
    width = max(segment.width for segment in incident)
    return any(_pad_on_layer(pad, layer) and
               point_to_pad_distance(node[0], node[1], pad) <=
               width / 2.0 + 1e-6
               for pad in pcb_data.pads_by_net.get(net_id, []))


def _walk_branch_chain(pcb_data, net_id, node, branch):
    """Walk from a T along its simple branch to the next KRT anchor."""
    net_segments = [segment for segment in pcb_data.segments
                    if segment.net_id == net_id and
                    not getattr(segment, "graphic", False)]
    group = [segment for segment in net_segments
             if segment.layer == branch.layer and
             abs(segment.width - branch.width) <= 1e-6 and
             not getattr(segment, "locked", False)]
    adjacency = defaultdict(list)
    actual = {}
    incidence = defaultdict(int)
    for segment in net_segments:
        incidence[pos_key(segment.start_x, segment.start_y)] += 1
        incidence[pos_key(segment.end_x, segment.end_y)] += 1
    for segment in group:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            key = pos_key(*point)
            adjacency[key].append(segment)
            actual[(id(segment), key)] = point
    via_keys = {pos_key(via.x, via.y) for via in pcb_data.vias
                if via.net_id == net_id}
    pads = pcb_data.pads_by_net.get(net_id, [])

    chain = []
    current = pos_key(*node)
    segment = branch
    used = set()
    anchor = node
    while len(chain) < 100:
        used.add(id(segment))
        chain.append(segment)
        a = pos_key(segment.start_x, segment.start_y)
        b = pos_key(segment.end_x, segment.end_y)
        other = b if a == current else a
        anchor = actual[(id(segment), other)]
        current = other
        anchored = (incidence[current] != 2 or current in via_keys or
                    any(_pad_on_layer(pad, branch.layer) and
                        point_to_pad_distance(anchor[0], anchor[1], pad) <=
                        branch.width / 2.0 + 1e-6 for pad in pads))
        if anchored:
            break
        following = [candidate for candidate in adjacency[current]
                     if id(candidate) not in used]
        if len(following) != 1:
            break
        segment = following[0]
    return chain, anchor


def _candidate_meets_only_rail_end(candidate, point, rails):
    """The moved branch may meet its rail once, at its final endpoint only."""
    from geometry_utils import segments_intersect
    last = candidate[-1]
    lv = (last.end_x - last.start_x, last.end_y - last.start_y)
    rv = _vector_from(point, rails[0])
    if abs(lv[0] * rv[1] - lv[1] * rv[0]) <= 1e-9:
        return False
    for segment in candidate[:-1]:
        if any(segments_intersect(
                segment.start_x, segment.start_y,
                segment.end_x, segment.end_y,
                rail.start_x, rail.start_y,
                rail.end_x, rail.end_y) for rail in rails):
            return False
    return True


def _best_slide(context, node, chain, anchor, rail_pairs, current, net_vias,
                foreign, deadline=None):
    branch = chain[0]
    old_length = calculate_route_length(chain)
    chain_ids = {id(segment) for segment in chain}
    best = None
    for rails in rail_pairs:
        if deadline is not None and perf_counter() >= deadline:
            break
        rail_ids = {id(segment) for segment in rails}
        outside = [segment for segment in current
                   if id(segment) not in chain_ids and id(segment) not in rail_ids]
        for point in _slide_positions(node, anchor, rails):
            if deadline is not None and perf_counter() >= deadline:
                break
            families = [("canonical", _candidate_segments(
                anchor, point, branch.layer, branch.width, branch.net_id))]
            families.extend(("sliding", family) for family in
                            _sliding_candidate_families(
                                anchor, point, branch.layer, branch.width,
                                branch.net_id, context.coord.grid_step))
            for source, family in families:
                if deadline is not None and perf_counter() >= deadline:
                    break
                for candidate in family:
                    if deadline is not None and perf_counter() >= deadline:
                        break
                    new_length = calculate_route_length(candidate)
                    if old_length - new_length <= context.coord.grid_step + 1e-12:
                        continue
                    if _new_boundary_right_angle(candidate, anchor, outside):
                        continue
                    if not _candidate_clears(context, foreign, candidate, source):
                        continue
                    if not _candidate_meets_only_rail_end(candidate, point, rails):
                        continue
                    if _touches_other_same_net(candidate, outside, net_vias,
                                               (anchor, point)):
                        continue
                    if any(pos_key(via.x, via.y) == pos_key(*point)
                           for via in net_vias):
                        continue
                    score = (new_length, len(candidate), point[0], point[1])
                    if best is None or score < best[0]:
                        best = score, candidate
    if best is not None and not context.clearance_adapter.connector_clears(
            best[1]):
        return None
    return None if best is None else best[1]


def slide_t_nodes(context, results, deadline=None):
    """Run one deterministic net-by-net G3.3 pass without moving any rail."""
    started = perf_counter()
    changes = GlossChanges()
    strips = []
    added_all = []
    saved_mm = 0.0
    changed_net_ids = set()
    branches_slid = 0
    locked_nets = {segment.net_id for segment in context.pcb_data.segments
                   if getattr(segment, "locked", False)}

    for net_id in context.net_ids:
        if deadline is not None and perf_counter() >= deadline:
            break
        if net_id in locked_nets:
            continue
        own_cache = context.net_obstacles.get(net_id)
        foreign = context.working_obstacles.clone_fresh()
        if own_cache is not None:
            remove_net_obstacles_from_cache(foreign, own_cache)
        nodes = defaultdict(list)
        for segment in context.pcb_data.segments:
            if (segment.net_id != net_id or
                    getattr(segment, "graphic", False)):
                continue
            nodes[(segment.layer, pos_key(segment.start_x,
                                          segment.start_y))].append(segment)
            nodes[(segment.layer, pos_key(segment.end_x,
                                          segment.end_y))].append(segment)
        processed = set()
        net_changed = False

        for (layer, node), initial_incident in sorted(nodes.items()):
            if deadline is not None and perf_counter() >= deadline:
                break
            if len(initial_incident) < 3 or _node_is_fixed(
                    context.pcb_data, net_id, layer, node, initial_incident):
                continue
            for branch in list(initial_incident):
                if deadline is not None and perf_counter() >= deadline:
                    break
                if id(branch) in processed or not any(
                        current is branch for current in context.pcb_data.segments):
                    continue
                others = [segment for segment in initial_incident
                          if segment is not branch and any(
                              current is segment
                              for current in context.pcb_data.segments)]
                rail_pairs = [pair for pair in combinations(others, 2)
                              if _opposite_collinear(node, pair[0], pair[1])]
                if not rail_pairs:
                    continue
                current = [segment for segment in context.pcb_data.segments
                           if segment.net_id == net_id]
                net_vias = [via for via in context.pcb_data.vias
                            if via.net_id == net_id]
                chain, anchor = _walk_branch_chain(
                    context.pcb_data, net_id, node, branch)
                candidate = _best_slide(
                    context, node, chain, anchor, rail_pairs, current, net_vias,
                    foreign, deadline=deadline)
                if candidate is None:
                    continue
                removed_ids = {id(segment) for segment in chain}
                before_grade = check_net_connectivity(
                    net_id, current, net_vias,
                    context.pcb_data.pads_by_net.get(net_id, []), [],
                    pcb_data=context.pcb_data)
                trial = [segment for segment in current
                         if id(segment) not in removed_ids] + candidate
                after_grade = check_net_connectivity(
                    net_id, trial, net_vias,
                    context.pcb_data.pads_by_net.get(net_id, []), [],
                    pcb_data=context.pcb_data)
                if _connectivity_worse(before_grade, after_grade):
                    continue

                strips.extend(_remove_result_custody(results, chain))
                context.pcb_data.segments = [
                    segment for segment in context.pcb_data.segments
                    if id(segment) not in removed_ids] + candidate
                if hasattr(context.pcb_data, "_foreign_seg_arr_cache"):
                    context.pcb_data._foreign_seg_arr_cache = None
                processed.update(removed_ids)
                changes.segments.extend({"old": segment, "stage": "G3.3"}
                                        for segment in chain)
                changes.segments.extend({"new": segment, "stage": "G3.3"}
                                        for segment in candidate)
                added_all.extend(candidate)
                saved_mm += calculate_route_length(chain) - \
                    calculate_route_length(candidate)
                changed_net_ids.add(net_id)
                branches_slid += 1
                net_changed = True

        if net_changed:
            if own_cache is not None:
                remove_net_obstacles_from_cache(context.working_obstacles,
                                                own_cache)
            new_cache = precompute_net_obstacles(
                context.pcb_data, net_id, context.config, extra_clearance=0.0)
            context.net_obstacles[net_id] = new_cache
            add_net_obstacles_from_cache(context.working_obstacles, new_cache)

    stats = {"t_branches_slid": branches_slid,
             "net_ids_changed": changed_net_ids,
             "saved_mm": round(saved_mm, 4),
             "algorithm_ms": round((perf_counter() - started) * 1000.0, 3)}
    return strips, added_all, changes, stats
