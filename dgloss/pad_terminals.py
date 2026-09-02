"""G3.2: simplify simple terminal chains up to the pad's native centre."""

from collections import defaultdict
from time import perf_counter

from check_connected import check_net_connectivity
from check_drc import point_to_pad_distance
from net_queries import calculate_route_length
from obstacle_cache import (add_net_obstacles_from_cache,
                            precompute_net_obstacles,
                            remove_net_obstacles_from_cache)
from routing_utils import pos_key

from .algorithm import (_candidate_clears, _candidate_segments,
                        _connectivity_worse, _edge_directions,
                        _remove_result_custody, _right_angle,
                        _sliding_candidate_families,
                        _touches_other_same_net)
from .changes import GlossChanges


def _pad_on_layer(pad, layer):
    return layer in (pad.layers or []) or "*.Cu" in (pad.layers or [])


def _endpoint_in_pad(segment, pad):
    if not _pad_on_layer(pad, segment.layer):
        return []
    points = []
    for point in ((segment.start_x, segment.start_y),
                  (segment.end_x, segment.end_y)):
        if point_to_pad_distance(point[0], point[1], pad) <= \
                segment.width / 2.0 + 1e-6:
            points.append(point)
    return points


def _walk_terminal_chain(pcb_data, net_id, pad):
    """Return one conservative same-layer/width chain leaving ``pad``."""
    net_segments = [segment for segment in pcb_data.segments
                    if segment.net_id == net_id and
                    not getattr(segment, "graphic", False)]
    contacts = []
    for segment in net_segments:
        for point in _endpoint_in_pad(segment, pad):
            contacts.append((segment, point))
    # Multiple copper entries make this a pad node, not a G3.2 simple terminal.
    contact_keys = {(id(segment), pos_key(*point))
                    for segment, point in contacts}
    if len(contact_keys) != 1:
        return None
    first, terminal = contacts[0]
    if getattr(first, "locked", False):
        return None

    layer, width = first.layer, first.width
    group = [segment for segment in net_segments
             if segment.layer == layer and
             abs(segment.width - width) <= 1e-6 and
             not getattr(segment, "locked", False)]
    adjacency = defaultdict(list)
    actual = {}
    total_incidence = defaultdict(int)
    for segment in net_segments:
        total_incidence[pos_key(segment.start_x, segment.start_y)] += 1
        total_incidence[pos_key(segment.end_x, segment.end_y)] += 1
    for segment in group:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            key = pos_key(*point)
            adjacency[key].append(segment)
            actual[(id(segment), key)] = point

    via_keys = {pos_key(via.x, via.y) for via in pcb_data.vias
                if via.net_id == net_id}
    other_pads = [other for other in pcb_data.pads_by_net.get(net_id, [])
                  if other is not pad]

    chain = []
    points = [terminal]
    current = pos_key(*terminal)
    segment = first
    used = set()
    while len(chain) < 100:
        used.add(id(segment))
        chain.append(segment)
        a = pos_key(segment.start_x, segment.start_y)
        b = pos_key(segment.end_x, segment.end_y)
        other_key = b if a == current else a
        other_point = actual[(id(segment), other_key)]
        points.append(other_point)
        current = other_key
        if (total_incidence[current] != 2 or current in via_keys or
                any(_pad_on_layer(other, layer) and
                    point_to_pad_distance(other_point[0], other_point[1], other)
                    <= width / 2.0 + 1e-6 for other in other_pads)):
            break
        following = [candidate for candidate in adjacency[current]
                     if id(candidate) not in used]
        if len(following) != 1:
            break
        segment = following[0]
    return chain, points


def _new_boundary_right_angle(candidate, anchor, outside):
    if not candidate:
        return False
    start = candidate[0].start_x, candidate[0].start_y
    _first, direction = _edge_directions(candidate, start, anchor)
    anchor_key = pos_key(*anchor)
    for sibling in outside:
        if sibling.layer != candidate[-1].layer:
            continue
        if anchor_key == pos_key(sibling.start_x, sibling.start_y):
            vector = (sibling.end_x - sibling.start_x,
                      sibling.end_y - sibling.start_y)
        elif anchor_key == pos_key(sibling.end_x, sibling.end_y):
            vector = (sibling.start_x - sibling.end_x,
                      sibling.start_y - sibling.end_y)
        else:
            continue
        sibling_direction = tuple(
            0 if abs(value) <= 1e-9 else (1 if value > 0 else -1)
            for value in vector)
        if _right_angle(direction, sibling_direction):
            return True
    return False


def _best_pad_connector(context, pad, chain, points, outside, net_vias,
                        foreign, deadline=None):
    centre = (pad.global_x, pad.global_y)
    anchor = points[-1]
    old_length = calculate_route_length(chain)
    families = [("canonical", _candidate_segments(
        centre, anchor, chain[0].layer, chain[0].width, chain[0].net_id))]
    families.extend(("sliding", family) for family in
                    _sliding_candidate_families(
                        centre, anchor, chain[0].layer, chain[0].width,
                        chain[0].net_id, context.coord.grid_step))
    best = None
    for source, family in families:
        if deadline is not None and perf_counter() >= deadline:
            break
        for candidate in family:
            if deadline is not None and perf_counter() >= deadline:
                break
            new_length = calculate_route_length(candidate)
            if old_length - new_length <= context.coord.grid_step + 1e-12:
                continue
            if not _candidate_clears(
                    context, foreign, candidate, source, chain):
                continue
            if _touches_other_same_net(candidate, outside, net_vias,
                                       (centre, anchor)):
                continue
            if _new_boundary_right_angle(candidate, anchor, outside):
                continue
            score = (new_length, len(candidate))
            if best is None or score < best[0]:
                best = score, candidate
    if best is None:
        return None
    candidate = best[1]
    if not context.clearance_adapter.connector_clears(candidate):
        return None
    return candidate


def optimize_pad_terminals(context, results, deadline=None):
    """One deterministic G3.2 pass; pads stay fixed and terminate the walk."""
    started = perf_counter()
    changes = GlossChanges()
    strips = []
    added_all = []
    saved_mm = 0.0
    changed_net_ids = set()
    pads_changed = 0
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
        net_changed = False
        processed = set()

        for pad in context.pcb_data.pads_by_net.get(net_id, []):
            if deadline is not None and perf_counter() >= deadline:
                break
            walked = _walk_terminal_chain(context.pcb_data, net_id, pad)
            if walked is None:
                continue
            chain, points = walked
            if not chain or any(id(segment) in processed for segment in chain):
                continue
            removed_ids = {id(segment) for segment in chain}
            current = [segment for segment in context.pcb_data.segments
                       if segment.net_id == net_id]
            outside = [segment for segment in current
                       if id(segment) not in removed_ids]
            net_vias = [via for via in context.pcb_data.vias
                        if via.net_id == net_id]
            candidate = _best_pad_connector(
                context, pad, chain, points, outside, net_vias, foreign,
                deadline=deadline)
            if candidate is None:
                continue

            before_grade = check_net_connectivity(
                net_id, current, net_vias,
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            trial = outside + candidate
            after_grade = check_net_connectivity(
                net_id, trial, net_vias,
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            if _connectivity_worse(before_grade, after_grade):
                continue

            strips.extend(_remove_result_custody(results, chain))
            context.pcb_data.segments = [segment for segment in
                                         context.pcb_data.segments
                                         if id(segment) not in removed_ids] + candidate
            if hasattr(context.pcb_data, "_foreign_seg_arr_cache"):
                context.pcb_data._foreign_seg_arr_cache = None
            processed.update(removed_ids)
            changes.segments.extend({"old": segment, "stage": "G3.2"}
                                    for segment in chain)
            changes.segments.extend({"new": segment, "stage": "G3.2"}
                                    for segment in candidate)
            added_all.extend(candidate)
            saved_mm += calculate_route_length(chain) - \
                calculate_route_length(candidate)
            changed_net_ids.add(net_id)
            pads_changed += 1
            net_changed = True

        if net_changed:
            if own_cache is not None:
                remove_net_obstacles_from_cache(context.working_obstacles,
                                                own_cache)
            new_cache = precompute_net_obstacles(
                context.pcb_data, net_id, context.config, extra_clearance=0.0)
            context.net_obstacles[net_id] = new_cache
            add_net_obstacles_from_cache(context.working_obstacles, new_cache)

    stats = {"pads_changed": pads_changed,
             "net_ids_changed": changed_net_ids,
             "saved_mm": round(saved_mm, 4),
             "algorithm_ms": round((perf_counter() - started) * 1000.0, 3)}
    return strips, added_all, changes, stats
