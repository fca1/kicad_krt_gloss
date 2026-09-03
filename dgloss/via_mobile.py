"""G3.1/G3.4: move simple two-layer vias with KRT geometry and checks."""

import math
from collections import defaultdict
from dataclasses import replace
from time import perf_counter

from check_connected import check_net_connectivity
from kicad_parser import Segment
from net_queries import calculate_route_length
from routing_utils import pos_key

from .algorithm import (_clears_krt_grid, _connectivity_worse, _right_angle,
                        _touches_other_same_net)
from .changes import GlossChanges, release_result_custody


_DIRECTIONS = ((1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, -1.0))


def _other_end(segment, at):
    if pos_key(segment.start_x, segment.start_y) == at:
        return segment.end_x, segment.end_y
    return segment.start_x, segment.start_y


def _octolinear(a, b):
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    return dx <= 1e-7 or dy <= 1e-7 or abs(dx - dy) <= 1e-7


def _line_intersection(a, u, b, v):
    denominator = u[0] * v[1] - u[1] * v[0]
    if abs(denominator) <= 1e-12:
        return None
    t = ((b[0] - a[0]) * v[1] - (b[1] - a[1]) * v[0]) / denominator
    return a[0] + t * u[0], a[1] + t * u[1]


def _candidate_positions(context, first_anchor, second_anchor, old_position):
    """Finite analytic intersections, with KRT's grid step as gain resolution.

    KRT's own smooth preserves off-grid terminal coordinates and computes its
    octolinear bends from them.  A mobile via is such a terminal on both layers:
    snapping it to the board's absolute grid would make both legs non-octolinear
    on ordinary imported KiCad copper.  There is no micron search here; the
    finite intersections come directly from the two KRT chain anchors.
    """
    candidates = {pos_key(*old_position): old_position}
    for first_direction in _DIRECTIONS:
        for second_direction in _DIRECTIONS:
            point = _line_intersection(first_anchor, first_direction,
                                       second_anchor, second_direction)
            if point is None:
                continue
            resolved = round(point[0], 6), round(point[1], 6)
            if (_octolinear(first_anchor, resolved) and
                    _octolinear(second_anchor, resolved)):
                candidates[pos_key(*resolved)] = resolved
    return list(candidates.values())


def _segment(anchor, via_position, source):
    if pos_key(*anchor) == pos_key(*via_position):
        return None
    return Segment(anchor[0], anchor[1], via_position[0], via_position[1],
                   source.width, source.layer, source.net_id)


def _direction_from(anchor, segment):
    other = _other_end(segment, pos_key(*anchor))
    dx, dy = other[0] - anchor[0], other[1] - anchor[1]
    return tuple(0 if abs(value) <= 1e-9 else (1 if value > 0 else -1)
                 for value in (dx, dy))


def _creates_boundary_right_angle(candidate, anchor, outside):
    if candidate is None:
        return False
    direction = _direction_from(anchor, candidate)
    for sibling in outside:
        if sibling.layer != candidate.layer:
            continue
        key = pos_key(*anchor)
        if key not in (pos_key(sibling.start_x, sibling.start_y),
                       pos_key(sibling.end_x, sibling.end_y)):
            continue
        if _right_angle(direction, _direction_from(anchor, sibling)):
            return True
    return False


def move_mobile_vias(context, results, *, net_ids, stage="G3.1",
                     full_chains=False, deadline=None):
    """Move only unlocked vias having exactly two unlocked cross-layer legs.

    G3.1 considers the two incident segments.  G3.4 uses the same operation and
    KRT predicates but follows both simple chains to their next native anchor.
    """
    started = perf_counter()
    changes = GlossChanges()
    input_vias = []
    emitted_vias = []
    segment_strips = []
    added_segments = []
    saved_mm = 0.0
    changed_net_ids = set()

    for net_id in net_ids:
        if deadline is not None and perf_counter() >= deadline:
            break
        foreign = context.foreign_obstacles(net_id)

        net_changed = False
        for old_via in list(context.pcb_data.vias):
            if deadline is not None and perf_counter() >= deadline:
                break
            if old_via.net_id != net_id or getattr(old_via, "locked", False):
                continue
            via_key = pos_key(old_via.x, old_via.y)
            net_segments = [segment for segment in context.pcb_data.segments
                            if segment.net_id == net_id]
            incident = [segment for segment in net_segments
                        if via_key in (pos_key(segment.start_x, segment.start_y),
                                       pos_key(segment.end_x, segment.end_y))]
            if (len(incident) != 2 or incident[0].layer == incident[1].layer or
                    any(getattr(segment, "locked", False) for segment in incident)):
                continue

            chains = [[segment] for segment in incident]
            anchors = [_other_end(segment, via_key) for segment in incident]
            if full_chains:
                # Local import avoids making the two small topology modules
                # depend on each other while reusing G3.3's already-tested
                # simple-chain walker.
                from .sliding_nodes import _walk_branch_chain
                walked = [_walk_branch_chain(
                    context.pcb_data, net_id, (old_via.x, old_via.y), segment)
                           for segment in incident]
                chains = [item[0] for item in walked]
                anchors = [item[1] for item in walked]
            removed_segments = [segment for chain in chains for segment in chain]
            removed_ids = {id(segment) for segment in removed_segments}
            outside = [segment for segment in net_segments
                       if id(segment) not in removed_ids]
            other_vias = [via for via in context.pcb_data.vias
                          if via.net_id == net_id and via is not old_via]
            old_length = calculate_route_length(removed_segments)
            best = None
            for position in _candidate_positions(
                    context, anchors[0], anchors[1], (old_via.x, old_via.y)):
                if deadline is not None and perf_counter() >= deadline:
                    break
                if pos_key(*position) == via_key:
                    continue
                legs = [_segment(anchors[index], position, incident[index])
                        for index in range(2)]
                candidate = [leg for leg in legs if leg is not None]
                new_length = calculate_route_length(candidate)
                if old_length - new_length <= context.coord.grid_step + 1e-12:
                    continue
                if any(calculate_route_length([leg]) <
                       context.coord.grid_step - 1e-9 for leg in candidate):
                    continue
                if (_creates_boundary_right_angle(legs[0], anchors[0], outside) or
                        _creates_boundary_right_angle(legs[1], anchors[1], outside)):
                    continue
                # The KRT grid is only a strict, inexpensive rejection filter.
                # Survivors are still certified by KRT's exact geometry below.
                if full_chains and not _clears_krt_grid(
                        context, foreign, candidate):
                    continue
                if not context.clearance_adapter.connector_clears(candidate):
                    continue
                if _touches_other_same_net(candidate, outside, other_vias,
                                           tuple(anchors)):
                    continue
                moved_via = replace(old_via, x=position[0], y=position[1], uuid="")
                if not context.clearance_adapter.via_clears(
                        moved_via, ignored_via=old_via):
                    continue
                score = (new_length, len(candidate), position[0], position[1])
                if best is None or score < best[0]:
                    best = score, moved_via, candidate
            if best is None:
                continue

            _score, moved_via, candidate = best
            before_grade = check_net_connectivity(
                net_id, net_segments,
                [via for via in context.pcb_data.vias if via.net_id == net_id],
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            trial_segments = outside + candidate
            trial_vias = [via for via in context.pcb_data.vias
                          if via.net_id == net_id and via is not old_via] + [moved_via]
            after_grade = check_net_connectivity(
                net_id, trial_segments, trial_vias,
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            if _connectivity_worse(before_grade, after_grade):
                continue

            strips, native_vias = release_result_custody(
                results, removed_segments, [old_via])
            segment_strips.extend(strips)
            if native_vias:
                input_vias.append(old_via)
            context.pcb_data.segments = [segment for segment in context.pcb_data.segments
                                         if id(segment) not in removed_ids] + candidate
            context.pcb_data.vias = [via for via in context.pcb_data.vias
                                     if via is not old_via] + [moved_via]
            if hasattr(context.pcb_data, "_foreign_seg_arr_cache"):
                context.pcb_data._foreign_seg_arr_cache = None
            changes.segments.extend({"old": segment, "stage": stage}
                                    for segment in removed_segments)
            changes.segments.extend({"new": segment, "stage": stage}
                                    for segment in candidate)
            changes.vias.append({"old": old_via, "new": moved_via,
                                 "stage": stage})
            emitted_vias.append(moved_via)
            added_segments.extend(candidate)
            saved_mm += old_length - calculate_route_length(candidate)
            changed_net_ids.add(net_id)
            net_changed = True

        if net_changed:
            context.refresh_net_obstacles(net_id)

    stats = {"vias_moved": len(changes.vias),
             "saved_mm": round(saved_mm, 4),
             "net_ids_changed": changed_net_ids,
             "algorithm_ms": round((perf_counter() - started) * 1000.0, 3),
             "segment_strips": segment_strips,
             "added_segments": added_segments}
    return input_vias, emitted_vias, changes, stats


def refine_mobile_vias(context, results, deadline=None, *, net_ids):
    """G3.4: jointly optimize both complete portions around a mobile via."""
    return move_mobile_vias(context, results, stage="G3.4", full_chains=True,
                            deadline=deadline, net_ids=net_ids)
