"""G3.1/G3.4: move simple two-layer vias with KRT geometry and checks."""

import math
from collections import deque
from dataclasses import replace
from .execution import perf_counter
from .topology import check_local_connectivity as check_net_connectivity
from dgloss.krt_api import (Segment, SpatialIndex, calculate_route_length,
                            point_to_pad_distance, point_to_segment_distance,
                            pos_key, via_copper_layers)
from dgloss.pad_terminals import _pad_on_layer
from .algorithm import (_clears_krt_grid)
from .route_geometry import (_right_angle, _touches_other_same_net)
from .topology import _connectivity_worse
from .changes import GlossChanges, release_result_custody
from .route_geometry import _DIRECTIONS
from .route_geometry import (_other_end, _line_intersection)


def _terminal_at_pad(context, via, layer, width):
    """Whether the absorbed leg ends on same-net pad copper on its layer."""
    index = getattr(context, "_progressive_pad_index", None)
    if index is None:
        pcb = context.pcb_data
        index = SpatialIndex(cell_size=max(
            1.0, max((item.width / 2 + 1e-6 for item in pcb.segments), default=0.0)))
        layers = pcb.board_info.copper_layers
        for net_id, pads in pcb.pads_by_net.items():
            for pad in pads:
                index.add_pad(pad, net_id,
                              [layer for layer in layers if _pad_on_layer(pad, layer)])
        context._progressive_pad_index = index
    return any(
        net_id == via.net_id and
        point_to_pad_distance(via.x, via.y, pad) <= width / 2 + 1e-6
        for pad, net_id in index.get_nearby_pads(via.x, via.y, layer))


def _progressing_vias(context, net_id):
    """Yield mobile vias again after a segment absorption creates a new leg."""
    pcb = context.pcb_data
    if not hasattr(context, "_absorbed_pad_vias"):
        context._absorbed_pad_vias = set()
    queue = deque(via for via in pcb.vias if via.net_id == net_id)
    while queue:
        old_via = queue.popleft()
        if (net_id, pos_key(old_via.x, old_via.y)) in context._absorbed_pad_vias:
            continue
        before_vias, before_segments = pcb.vias, pcb.segments
        yield old_via
        if pcb.vias is before_vias:
            continue
        previous_ids = {id(via) for via in before_vias}
        anchors = {
            _other_end(segment, pos_key(old_via.x, old_via.y))
            for segment in before_segments
            if segment.net_id == net_id and pos_key(old_via.x, old_via.y) in
            (pos_key(segment.start_x, segment.start_y),
             pos_key(segment.end_x, segment.end_y))
        }
        added = [via for via in pcb.vias
                 if id(via) not in previous_ids and via.net_id == net_id]
        if len(added) != 1 or (added[0].x, added[0].y) not in anchors:
            continue
        moved_via = added[0]
        if (net_id, pos_key(moved_via.x, moved_via.y)) in context._absorbed_pad_vias:
            continue
        touching = [
            segment for segment in pcb.segments
            if segment.net_id == net_id and
            segment.layer in via_copper_layers(
                moved_via, pcb.board_info.copper_layers) and
            point_to_segment_distance(
                moved_via.x, moved_via.y, segment.start_x, segment.start_y,
                segment.end_x, segment.end_y) <= 1e-7
        ]
        if (len(touching) != 2 or touching[0].layer == touching[1].layer or
                any(getattr(segment, "locked", False) or
                    getattr(segment, "graphic", False) for segment in touching) or
                any(via is not moved_via and
                    pos_key(via.x, via.y) == pos_key(moved_via.x, moved_via.y)
                    for via in pcb.vias)):
            continue
        queue.appendleft(moved_via)


def _octolinear(a, b):
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    return dx <= 1e-7 or dy <= 1e-7 or abs(dx - dy) <= 1e-7


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
    stage_segments = {id(segment) for segment in context.pcb_data.segments}
    stage_vias = {id(via) for via in context.pcb_data.vias}
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
        for old_via in _progressing_vias(context, net_id):
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
                from .chain_topology import _walk_branch_chain
                walked = [_walk_branch_chain(
                    context.pcb_data, net_id, (old_via.x, old_via.y), segment)
                           for segment in incident]
                chains = [item[0] for item in walked]
                anchors = [item[1] for item in walked]
            removed_segments = [segment for chain in chains for segment in chain]
            if not context.segments_editable(removed_segments):
                continue
            removed_ids = {id(segment) for segment in removed_segments}
            outside = [segment for segment in net_segments
                       if id(segment) not in removed_ids]
            other_vias = [via for via in context.pcb_data.vias
                          if via.net_id == net_id and via is not old_via]
            old_length = calculate_route_length(removed_segments)
            best = None
            before_grade = None
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
                score = (new_length, len(candidate),
                         math.hypot(position[0] - old_via.x,
                                    position[1] - old_via.y),
                         position[0], position[1])
                if best is not None and score >= best[0]:
                    continue
                if any(calculate_route_length([leg]) <
                       context.coord.grid_step - 1e-9 for leg in candidate):
                    continue
                if (_creates_boundary_right_angle(legs[0], anchors[0], outside) or
                        _creates_boundary_right_angle(legs[1], anchors[1], outside)):
                    continue
                # The KRT grid is only a strict, inexpensive rejection filter.
                # Survivors are still certified by KRT's exact geometry below.
                if candidate and full_chains and not _clears_krt_grid(
                        context, foreign, candidate):
                    continue
                if candidate and not context.clearance_adapter.connector_clears(candidate):
                    continue
                if _touches_other_same_net(candidate, outside, other_vias,
                                           tuple(anchors)):
                    continue
                moved_via = replace(old_via, x=position[0], y=position[1], uuid="")
                if not context.clearance_adapter.via_clears(
                        moved_via, ignored_via=old_via):
                    continue
                motion = getattr(context, "_reduction_motion", None)
                if motion is not None and not motion.via(
                        context, chains, anchors, old_via, moved_via, legs, deadline):
                    continue
                if before_grade is None:
                    before_grade = check_net_connectivity(
                        net_id, net_segments, other_vias + [old_via],
                        context.pcb_data.pads_by_net.get(net_id, []), [],
                        pcb_data=context.pcb_data)
                after_grade = check_net_connectivity(
                    net_id, outside + candidate, other_vias + [moved_via],
                    context.pcb_data.pads_by_net.get(net_id, []), [],
                    pcb_data=context.pcb_data)
                if _connectivity_worse(before_grade, after_grade):
                    continue
                best = score, moved_via, candidate
            if best is None:
                continue

            _score, moved_via, candidate = best
            # Remember actual terminal absorption across G3.1, G3.4 and
            # subsequent passes. Mere via/pad contact is not a stop event.
            if any(pos_key(moved_via.x, moved_via.y) == pos_key(*anchor) and
                   _terminal_at_pad(context, moved_via, chain[-1].layer,
                                    chain[-1].width)
                   for anchor, chain in zip(anchors, chains)):
                context._absorbed_pad_vias.add(
                    (net_id, pos_key(moved_via.x, moved_via.y)))
            strips, native_vias = release_result_custody(
                results, removed_segments, [old_via])
            segment_strips.extend(strips)
            if native_vias:
                input_vias.append(old_via)
            context.apply_replacement(removed_segments, candidate,
                                      [old_via], [moved_via])
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

    # Do not export intermediate copper that was later absorbed in this stage.
    live_segments = {id(segment) for segment in context.pcb_data.segments}
    live_vias = {id(via) for via in context.pcb_data.vias}
    input_vias = [via for via in input_vias if id(via) in stage_vias]
    emitted_vias = [via for via in emitted_vias if id(via) in live_vias]
    segment_strips = [segment for segment in segment_strips
                      if id(segment) in stage_segments]
    added_segments = [segment for segment in added_segments
                      if id(segment) in live_segments]
    changes.segments = [change for change in changes.segments
                        if ("old" in change and id(change["old"]) in stage_segments) or
                        ("new" in change and id(change["new"]) in live_segments)]
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
