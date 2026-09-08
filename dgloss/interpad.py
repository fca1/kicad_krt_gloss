"""G3.6: detect and center tracks crossing two-pad gates.

KRT owns pad geometry, copper-layer expansion and the spatial index.  This
module combines those existing operations and integrates accepted candidates
into dgloss; it does not implement a new Rust primitive.
"""

import heapq
import math
from time import perf_counter
from dgloss.krt_api import check_net_connectivity
from .changes import GlossChanges, release_result_custody
from .interpad_types import (InterpadDoor, InterpadScan, InterpadCandidate)
from .interpad_geometry import (_intersection, _edge_towards, _pair_clearance, _cross,
    _point, _other_end, _octolinear, _axis_to_pad_distance, _segment_pad_distance,
    door_crossing_options, door_crossing_direction, _line_intersection, _native_pad_at)
from .interpad_paths import (center_with_sliding_neighbors, center_across_multiple_doors,
    center_across_branch_doors)
from .interpad_detection import (find_interpad_doors)


def _door_key(door):
    pads = sorted((id(door.pad_a), id(door.pad_b)))
    return pads[0], pads[1], door.layer


def _branch_door_groups(pcb_data, doors):
    """Group doors by their same-layer connected track component."""
    by_layer = {}
    for door in doors:
        by_layer.setdefault(door.layer, []).append(door)
    groups = []
    for layer_doors in by_layer.values():
        segments = [segment for segment in pcb_data.segments
                    if segment.net_id == layer_doors[0].segment.net_id and
                    segment.layer == layer_doors[0].layer and
                    not getattr(segment, "graphic", False)]

        def key(point):
            return round(point[0], 7), round(point[1], 7)

        incidence = {}
        for segment in segments:
            for point in ((segment.start_x, segment.start_y),
                          (segment.end_x, segment.end_y)):
                incidence.setdefault(key(point), []).append(segment)
        component_by_id = {}
        component = 0
        for seed in segments:
            if id(seed) in component_by_id:
                continue
            component += 1
            pending = [seed]
            while pending:
                segment = pending.pop()
                if id(segment) in component_by_id:
                    continue
                component_by_id[id(segment)] = component
                for point in ((segment.start_x, segment.start_y),
                              (segment.end_x, segment.end_y)):
                    pending.extend(incidence.get(key(point), ()))
        grouped = {}
        for door in layer_doors:
            grouped.setdefault(component_by_id.get(id(door.segment)), []).append(
                door)
        groups.extend(tuple(group) for group in grouped.values()
                      if len(group) >= 2)
    groups.sort(key=lambda group: (
        len(group), sum(abs(door.offset) for door in group)), reverse=True)
    return groups


def _connected_segment_ids(pcb_data, seeds):
    """Return the same-net/layer component containing ``seeds``."""
    seeds = tuple(seeds)
    if not seeds:
        return set()
    net_id, layer = seeds[0].net_id, seeds[0].layer
    segments = [segment for segment in pcb_data.segments
                if segment.net_id == net_id and segment.layer == layer and
                not getattr(segment, "graphic", False)]

    def key(point):
        return round(point[0], 7), round(point[1], 7)

    incidence = {}
    for segment in segments:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            incidence.setdefault(key(point), []).append(segment)
    found = set()
    pending = list(seeds)
    while pending:
        segment = pending.pop()
        if id(segment) in found:
            continue
        found.add(id(segment))
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            pending.extend(incidence.get(key(point), ()))
    return found


def _ranked_direction_maps(doors, build_new_segments, limit=64):
    """Yield the best joint orientation choices without a Cartesian blow-up."""
    options = [door_crossing_options(
        door, allow_reorientation=build_new_segments) for door in doors]
    if not options or any(not values for values in options):
        return
    initial = tuple(0 for _ in options)
    pending = [(0, initial)]
    seen = {initial}
    emitted = 0
    while pending and emitted < limit:
        _rank, indices = heapq.heappop(pending)
        yield {id(door): options[index][choice]
               for index, (door, choice) in enumerate(zip(doors, indices))}
        emitted += 1
        for index, values in enumerate(options):
            if indices[index] + 1 >= len(values):
                continue
            neighbour = list(indices)
            neighbour[index] += 1
            neighbour = tuple(neighbour)
            if neighbour in seen:
                continue
            seen.add(neighbour)
            heapq.heappush(pending, (sum(neighbour), neighbour))


def _segment_set_signature(segments):
    rows = []
    for segment in segments:
        start = (round(segment.start_x, 7), round(segment.start_y, 7))
        end = (round(segment.end_x, 7), round(segment.end_y, 7))
        rows.append((min(start, end), max(start, end),
                     round(segment.width, 7), segment.layer, segment.net_id))
    return sorted(rows)


def _candidate_is_valid(context, candidate, before_grade, *, allow_unchanged=False):
    """Apply the common editability, geometry, KRT and topology gates."""
    if not context.segments_editable(candidate.source_segments):
        return False, None, "scope"
    if not allow_unchanged and _segment_set_signature(candidate.source_segments) == \
            _segment_set_signature(candidate.segments):
        return False, None, "unchanged"
    if any(math.hypot(segment.end_x - segment.start_x,
                      segment.end_y - segment.start_y) <
           context.coord.grid_step - 1e-9
           for segment in candidate.segments):
        return False, None, "grid"
    if not context.clearance_adapter.connector_clears(candidate.segments):
        return False, None, "clearance"

    source_ids = {id(segment) for segment in candidate.source_segments}
    current = [segment for segment in context.pcb_data.segments
               if segment.net_id == candidate.source_segments[0].net_id]
    outside = [segment for segment in current if id(segment) not in source_ids]
    boundary = []
    outside_points = {
        (round(point[0], 7), round(point[1], 7))
        for segment in outside
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y))}
    for segment in candidate.source_segments:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            if (round(point[0], 7), round(point[1], 7)) in outside_points:
                boundary.append(point)
    candidate_points = {
        (round(point[0], 7), round(point[1], 7))
        for segment in candidate.segments
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y))}
    for segment in candidate.source_segments:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            if (round(point[0], 7), round(point[1], 7)) in candidate_points:
                boundary.append(point)
    from .algorithm import _connectivity_worse, _touches_other_same_net
    vias = [via for via in context.pcb_data.vias
            if via.net_id == candidate.source_segments[0].net_id]
    if _touches_other_same_net(candidate.segments, outside, vias, boundary):
        return False, None, "same_net"

    trial = outside + list(candidate.segments)
    net_id = candidate.source_segments[0].net_id
    after_grade = check_net_connectivity(
        net_id, trial, vias, context.pcb_data.pads_by_net.get(net_id, []), [],
        pcb_data=context.pcb_data)
    if _connectivity_worse(before_grade, after_grade):
        return False, after_grade, "connectivity"
    return True, after_grade, None


def _centering_proposals(pcb_data, doors, *, build_new_segments,
                         build_multi_door_path):
    """Yield candidates in M01 priority order: most doors first."""
    ranked = sorted(doors, key=lambda door: abs(door.offset), reverse=True)
    if build_multi_door_path:
        for branch_doors in _branch_door_groups(pcb_data, ranked):
            for directions in _ranked_direction_maps(
                    branch_doors, build_new_segments):
                yield branch_doors, center_across_branch_doors(
                    pcb_data, branch_doors,
                    build_new_segments=build_new_segments,
                    crossing_directions=directions)
        by_segment = {}
        for door in ranked:
            by_segment.setdefault(id(door.segment), []).append(door)
        groups = [tuple(group) for group in by_segment.values()
                  if len(group) >= 2]
        groups.sort(key=lambda group: (
            len(group), sum(abs(door.offset) for door in group)), reverse=True)
        for group in groups:
            yield group, center_across_multiple_doors(
                pcb_data, group, build_new_segments=build_new_segments)
    for door in ranked:
        yield (door,), center_with_sliding_neighbors(
            pcb_data, door, build_new_segments=build_new_segments)


def center_interpad_routes(context, results, deadline=None, *, net_ids,
                           proximity_mm=1.0,
                           build_new_segments=False,
                           build_multi_door_path=False):
    """G3.6: center editable octolinear branches across valid pad doors.

    Detection and exact clearance use KRT's existing spatial and geometry
    primitives.  Door coverage has priority over copper length and segment
    count.  Every accepted replacement preserves connectivity and the common
    immutable/branch scope; final G5 certification remains authoritative.
    """
    started = perf_counter()
    changes = GlossChanges()
    input_strips = []
    added_segments = []
    changed_net_ids = set()
    processed_doors = set()
    candidates_tested = 0
    candidates_considered = 0
    doors_detected = 0
    rejected = {
        "construction": 0,
        "passage": 0,
        "scope": 0,
        "unchanged": 0,
        "grid": 0,
        "clearance": 0,
        "same_net": 0,
        "connectivity": 0,
    }
    length_delta = 0.0
    branches_centered = 0
    doors_already_centered = 0

    for net_id in net_ids:
        while deadline is None or perf_counter() < deadline:
            scan = find_interpad_doors(
                context.pcb_data, context.config, net_id=net_id,
                proximity_mm=proximity_mm, deadline=deadline,
                allowed_segment_ids=context.editable_segment_ids)
            doors = [door for door in scan.doors
                     if _door_key(door) not in processed_doors]
            doors_detected += len(doors)
            if not doors:
                break
            current = [segment for segment in context.pcb_data.segments
                       if segment.net_id == net_id]
            vias = [via for via in context.pcb_data.vias
                    if via.net_id == net_id]
            before_grade = check_net_connectivity(
                net_id, current, vias,
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            accepted = None
            def proposals():
                if build_multi_door_path and build_new_segments:
                    from .protected_centering import build_protected_path
                    for group in _branch_door_groups(context.pcb_data, doors):
                        yield group, build_protected_path(context, group, deadline)
                yield from _centering_proposals(
                    context.pcb_data, doors,
                    build_new_segments=build_new_segments,
                    build_multi_door_path=(build_multi_door_path and
                                           not build_new_segments))
                if build_new_segments:
                    from .interpad_paths import center_with_propagated_neighbors
                    for door in doors:
                        for candidate in center_with_propagated_neighbors(
                                context.pcb_data, door, deadline):
                            yield (door,), candidate
            for selected_doors, candidate in proposals():
                if deadline is not None and perf_counter() >= deadline:
                    break
                candidates_considered += 1
                if candidate is None:
                    rejected["construction"] += 1
                    continue
                from .protected_centering import certify_passages
                if not certify_passages(candidate, selected_doors):
                    rejected["passage"] += 1
                    continue
                candidates_tested += 1
                valid, _after_grade, reason = _candidate_is_valid(
                    context, candidate, before_grade, allow_unchanged=True)
                if valid:
                    accepted = selected_doors, candidate
                    break
                rejected[reason] += 1
            if accepted is None:
                processed_doors.update(_door_key(door) for door in doors)
                break

            selected_doors, candidate = accepted
            if _segment_set_signature(candidate.source_segments) == \
                    _segment_set_signature(candidate.segments):
                # A certified centered passage is satisfied, not a reason to
                # replace its approaches with a different, longer route.
                processed_doors.update(_door_key(d) for d in selected_doors)
                doors_already_centered += len(selected_doors)
                continue
            removed = list(candidate.source_segments)
            removed_ids = {id(segment) for segment in removed}
            built = list(candidate.segments)
            branch_ids = _connected_segment_ids(
                context.pcb_data, candidate.source_segments)
            processed_doors.update(
                _door_key(door) for door in doors
                if id(door.segment) in branch_ids)

            # Segments created earlier in this same G3.6 call are held locally
            # until the stage emits its result.  Do not strip them from the
            # native board, and do not emit obsolete intermediate geometry.
            local_ids = {id(segment) for segment in added_segments}
            added_segments[:] = [segment for segment in added_segments
                                  if id(segment) not in removed_ids]
            external_removed = [segment for segment in removed
                                if id(segment) not in local_ids]
            native, _native_vias = release_result_custody(
                results, external_removed)
            input_strips.extend(native)
            context.apply_replacement(removed, built)
            changes.segments.extend(
                {"old": segment, "stage": "G3.6"} for segment in removed)
            changes.segments.extend(
                {"new": segment, "stage": "G3.6"} for segment in built)
            changes.doors.extend(selected_doors)
            added_segments.extend(built)
            length_delta += candidate.after_length - candidate.before_length
            branches_centered += 1
            changed_net_ids.add(net_id)
            context.refresh_net_obstacles(net_id)

    stats = {
        "branches_centered": branches_centered,
        "doors_centered": len(changes.doors),
        "doors_already_centered": doors_already_centered,
        "segments_added": len(added_segments),
        "length_delta_mm": round(length_delta, 4),
        "net_ids_changed": changed_net_ids,
        "algorithm_ms": round((perf_counter() - started) * 1000.0, 3),
        "candidates_tested": candidates_tested,
        "candidates_considered": candidates_considered,
        "doors_detected": doors_detected,
        "candidate_rejections": rejected,
    }
    return input_strips, added_segments, changes, stats
