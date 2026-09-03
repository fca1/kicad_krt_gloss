"""G3: one-pass, fixed-via route-length reduction on KRT's grid."""

from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

from check_connected import check_net_connectivity
from check_drc import point_to_pad_distance
from geometry_utils import point_to_segment_distance, segments_intersect
from kicad_parser import Segment
from net_queries import calculate_route_length
from pcb_modification import _octolinear_bends
from routing_utils import pos_key
from single_ended_routing import _segment_fits_wide
from .changes import GlossChanges, release_result_custody


@dataclass
class _Chain:
    segments: list
    points: list
    layer: str
    width: float


def _connectivity_worse(before, after):
    """Use KRT's connectivity grade without requiring an initially clean net."""
    return ((before.get("connected") and not after.get("connected")) or
            len(after.get("disconnected_pads") or []) >
            len(before.get("disconnected_pads") or []) or
            (after.get("num_components") or 1) >
            (before.get("num_components") or 1))


def _pad_holds_point(pad, point, layer, half_width):
    if layer not in pad.layers and not any("*" in name for name in pad.layers):
        return False
    return point_to_pad_distance(point[0], point[1], pad) <= half_width + 1e-6


def _simple_chains(pcb_data, net_id):
    """Return conservative same-layer/width chains; pads, vias and nodes anchor."""
    net_segments = [s for s in pcb_data.segments if s.net_id == net_id and
                    not getattr(s, "graphic", False) and
                    not getattr(s, "locked", False)]
    if len(net_segments) < 2:
        return []

    incidence = defaultdict(int)
    for seg in [s for s in pcb_data.segments if s.net_id == net_id]:
        incidence[pos_key(seg.start_x, seg.start_y)] += 1
        incidence[pos_key(seg.end_x, seg.end_y)] += 1
    via_points = {pos_key(v.x, v.y) for v in pcb_data.vias if v.net_id == net_id}
    pads = pcb_data.pads_by_net.get(net_id, [])

    groups = defaultdict(list)
    for seg in net_segments:
        groups[(seg.layer, round(seg.width, 6))].append(seg)

    chains = []
    for (layer, width), segments in sorted(groups.items()):
        adjacency = defaultdict(list)
        actual = {}
        for seg in segments:
            a = pos_key(seg.start_x, seg.start_y)
            b = pos_key(seg.end_x, seg.end_y)
            adjacency[a].append(seg)
            adjacency[b].append(seg)
            actual[(id(seg), a)] = (seg.start_x, seg.start_y)
            actual[(id(seg), b)] = (seg.end_x, seg.end_y)

        def interior(key):
            point = actual.get((id(adjacency[key][0]), key), key)
            return (len(adjacency[key]) == 2 and incidence[key] == 2 and
                    key not in via_points and
                    not any(_pad_holds_point(pad, point, layer, width / 2)
                            for pad in pads))

        anchors = sorted(key for key in adjacency if not interior(key))
        used = set()
        for anchor in anchors:
            for first in adjacency[anchor]:
                if id(first) in used:
                    continue
                ordered = []
                points = [actual[(id(first), anchor)]]
                current = anchor
                seg = first
                while True:
                    used.add(id(seg))
                    ordered.append(seg)
                    a = pos_key(seg.start_x, seg.start_y)
                    b = pos_key(seg.end_x, seg.end_y)
                    other = b if a == current else a
                    points.append(actual[(id(seg), other)])
                    current = other
                    if current == anchor or not interior(current):
                        break
                    following = [candidate for candidate in adjacency[current]
                                 if id(candidate) not in used]
                    if not following:
                        break
                    seg = following[0]
                if current != anchor and len(ordered) >= 2:
                    chains.append(_Chain(ordered, points, layer, width))
    return chains


def _candidate_segments(a, b, layer, width, net_id):
    """Build KRT-octolinear connectors; dgloss owns only their selection."""
    for bends in _octolinear_bends(a, b):
        candidate = _segments_for_points([a] + bends + [b], layer, width,
                                         net_id)
        if candidate:
            yield candidate


def _segments_for_points(points, layer, width, net_id):
    return [Segment(start_x=points[i][0], start_y=points[i][1],
                    end_x=points[i + 1][0], end_y=points[i + 1][1],
                    width=width, layer=layer, net_id=net_id)
            for i in range(len(points) - 1)
            if pos_key(*points[i]) != pos_key(*points[i + 1])]


def _sliding_candidate_families(a, b, layer, width, net_id, grid_step):
    """Monotone axis/diagonal/axis paths, longest diagonal first on KRT's step."""
    diagonal_max = min(abs(b[0] - a[0]), abs(b[1] - a[1]))
    if diagonal_max <= grid_step + 1e-9:
        return
    # The diagonal must separate the two orthogonal moves.  Any other
    # permutation puts X and Y next to each other and creates a 90-degree
    # corner even though every individual segment is octolinear.
    orders = (("x", "d", "y"), ("y", "d", "x"))

    for order in orders:
        def family(order=order):
            index = 1
            while index * grid_step < diagonal_max - 1e-9:
                yield _sliding_candidate_at(
                    a, b, layer, width, net_id, grid_step, index, order)
                index += 1
        yield family()


def _sliding_candidate_at(a, b, layer, width, net_id, grid_step, index,
                          order):
    """Build one sliding candidate directly at an integer KRT-grid index."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    adx, ady = abs(dx), abs(dy)
    diagonal = min(adx, ady) - index * grid_step
    if diagonal <= 1e-9:
        return []
    sx = 1.0 if dx >= 0 else -1.0
    sy = 1.0 if dy >= 0 else -1.0
    moves = {
        "x": (sx * (adx - diagonal), 0.0),
        "y": (0.0, sy * (ady - diagonal)),
        "d": (sx * diagonal, sy * diagonal),
    }
    points = [a]
    x, y = a
    for kind in order:
        mx, my = moves[kind]
        if abs(mx) > 1e-9 or abs(my) > 1e-9:
            x, y = round(x + mx, 6), round(y + my, 6)
            points.append((x, y))
    points[-1] = b
    return _segments_for_points(points, layer, width, net_id)


def _last_positive_sliding_index(a, b, layer, width, net_id, grid_step,
                                 order, old_length):
    """Find the least-gain useful position without materializing the family."""
    diagonal_max = min(abs(b[0] - a[0]), abs(b[1] - a[1]))
    upper = max(0, int((diagonal_max - 1e-9) // grid_step))
    if upper < 1:
        return 0

    def improves(index):
        candidate = _sliding_candidate_at(
            a, b, layer, width, net_id, grid_step, index, order)
        return (bool(candidate) and
                calculate_route_length(candidate) < old_length - 1e-12)

    if not improves(1):
        return 0
    if improves(upper):
        return upper
    low, high = 1, upper
    while low + 1 < high:
        middle = (low + high) // 2
        if improves(middle):
            low = middle
        else:
            high = middle
    return low


def _adaptive_sliding_candidates(context, obstacles, a, b, layer, width,
                                 net_id, old_length):
    """Search the first locally reachable slide, five KRT cells at a time.

    The search starts next to the existing geometry and moves toward the
    shortest connector. A grid rejection gets KRT's exact confirmation; a
    confirmed first obstruction ends that family. Only the last five-cell
    interval is refined at the actual KRT grid step.
    """
    stride = 5
    orders = (("x", "d", "y"), ("y", "d", "x"))

    def candidate(index, order):
        return _sliding_candidate_at(
            a, b, layer, width, net_id, context.coord.grid_step, index, order)

    def clears(segments):
        if (not segments or any(
                calculate_route_length([segment]) <
                context.coord.grid_step - 1e-9 for segment in segments)):
            return False
        if _clears_krt_grid(context, obstacles, segments):
            return True
        return context.clearance_adapter.connector_clears(segments)

    for order in orders:
        last = _last_positive_sliding_index(
            a, b, layer, width, net_id, context.coord.grid_step, order,
            old_length)
        if not last:
            continue

        probe = max(1, last - stride)
        first = candidate(probe, order)
        if not clears(first):
            continue
        best = probe

        while best > 1:
            probe = max(1, best - stride)
            tested = candidate(probe, order)
            if clears(tested):
                best = probe
                continue

            # Move back from the first obstruction one real grid cell at a
            # time. Stop at the first valid point: anything beyond the
            # obstruction belongs to another local basin.
            for index in range(probe + 1, best):
                tested = candidate(index, order)
                if clears(tested):
                    best = index
                    break
            break
        yield candidate(best, order)


def _clears_krt_grid(context, obstacles, segments):
    """Fast G3 predicate using KRT's Rust map and KRT width margins."""
    if not segments:
        return False
    margins = context.config.track_margins_for_width(segments[0].width)
    for seg in segments:
        layer_idx = context.layer_map.get(seg.layer)
        if layer_idx is None or not _segment_fits_wide(
                seg, obstacles, context.coord, layer_idx, margins[layer_idx]):
            return False
    return True


def _reuses_source_segment(candidate, source_segments):
    """True when candidate is wholly contained in unchanged source copper."""
    return any(
        candidate.layer == source.layer and
        abs(candidate.width - source.width) <= 1e-6 and
        point_to_segment_distance(
            candidate.start_x, candidate.start_y,
            source.start_x, source.start_y,
            source.end_x, source.end_y) <= 1e-7 and
        point_to_segment_distance(
            candidate.end_x, candidate.end_y,
            source.start_x, source.start_y,
            source.end_x, source.end_y) <= 1e-7
        for source in source_segments)


def _candidate_clears(context, obstacles, segments, source,
                      source_segments=()):
    """G3 speed policy, explicitly split by candidate provenance.

    KRT's own canonical connectors use KRT's exact smooth predicate through the
    thin adapter.  The much larger dgloss sliding family is searched on KRT's
    Rust grid.  A grid rejection is confirmed by KRT's exact predicate only
    when every rejected segment is copper retained from the replaced source;
    genuinely new copper must always pass the grid.  Whatever the search
    source, the selected replacement is checked exactly once more before it can
    leave this module.
    """
    if any(calculate_route_length([segment]) < context.coord.grid_step - 1e-9
           for segment in segments):
        return False
    if source == "canonical":
        return context.clearance_adapter.connector_clears(segments)
    rejected = [segment for segment in segments
                if not _clears_krt_grid(context, obstacles, [segment])]
    if not rejected:
        return True
    if not source_segments or not all(
            _reuses_source_segment(segment, source_segments)
            for segment in rejected):
        return False
    return context.clearance_adapter.connector_clears(segments)


def _touches_other_same_net(candidate, outside, vias, allowed_ends):
    """Reject a new same-net junction: G3 changes length, never topology."""
    allowed = {pos_key(*point) for point in allowed_ends}
    for new in candidate:
        for old in outside:
            if new.layer != old.layer:
                continue
            if not segments_intersect(new.start_x, new.start_y,
                                      new.end_x, new.end_y,
                                      old.start_x, old.start_y,
                                      old.end_x, old.end_y):
                continue
            shared = ({pos_key(new.start_x, new.start_y),
                       pos_key(new.end_x, new.end_y)} &
                      {pos_key(old.start_x, old.start_y),
                       pos_key(old.end_x, old.end_y)})
            if not shared or not shared.issubset(allowed):
                return True
        for via in vias:
            key = pos_key(via.x, via.y)
            if key in allowed:
                continue
            if point_to_segment_distance(via.x, via.y,
                                         new.start_x, new.start_y,
                                         new.end_x, new.end_y) <= \
                    (getattr(via, "size", 0.0) + new.width) / 2.0:
                return True
    return False


def _edge_directions(segments, start, end):
    """Traversal directions of an ordered graph edge, including reversed input."""
    first, last = segments[0], segments[-1]
    if pos_key(first.start_x, first.start_y) == pos_key(*start):
        first_vector = (first.end_x - first.start_x,
                        first.end_y - first.start_y)
    else:
        first_vector = (first.start_x - first.end_x,
                        first.start_y - first.end_y)
    if pos_key(last.end_x, last.end_y) == pos_key(*end):
        last_vector = (last.end_x - last.start_x,
                       last.end_y - last.start_y)
    else:
        last_vector = (last.start_x - last.end_x,
                       last.start_y - last.end_y)

    def direction(vector):
        return tuple(0 if abs(value) <= 1e-9 else (1 if value > 0 else -1)
                     for value in vector)
    return direction(first_vector), direction(last_vector)


def _right_angle(first, second):
    return first[0] * second[0] + first[1] * second[1] == 0


def _best_chain_replacement(context, chain, net_id, foreign_obstacles,
                            net_segments, net_vias, deadline=None,
                            objective="shorter"):
    """Shortest valid path through a chain's ordered vertices (DAG dynamic program)."""
    n = len(chain.segments)
    span_ids = {id(seg) for seg in chain.segments}
    outside = [seg for seg in net_segments if id(seg) not in span_ids]
    edges = defaultdict(list)

    # Keeping an original edge is always a valid option.
    for i, seg in enumerate(chain.segments):
        edges[i].append((i + 1, [seg], False,
                         calculate_route_length([seg])))

    min_gain = context.coord.grid_step
    for i in range(n - 1):
        if deadline is not None and perf_counter() >= deadline:
            break
        for j in range(i + 2, n + 1):
            if deadline is not None and perf_counter() >= deadline:
                break
            old_length = calculate_route_length(chain.segments[i:j])
            families = [("canonical", _candidate_segments(
                chain.points[i], chain.points[j], chain.layer, chain.width,
                net_id))]
            if objective == "shorter":
                families.append(("sliding_exact", _adaptive_sliding_candidates(
                    context, foreign_obstacles, chain.points[i], chain.points[j],
                    chain.layer, chain.width, net_id, old_length)))
            for source, family in families:
                if deadline is not None and perf_counter() >= deadline:
                    break
                for candidate in family:
                    if deadline is not None and perf_counter() >= deadline:
                        break
                    new_length = calculate_route_length(candidate)
                    gain = old_length - new_length
                    if objective == "fewer_segments":
                        # A one-segment equal replacement is an exact
                        # collinear merge; leave it to KRT's purpose-built
                        # merge_collinear_segments() final pass.
                        if (len(candidate) == 1 or abs(gain) > 1e-9 or
                                len(candidate) >= j - i):
                            continue
                    # Families are shortest-first. Once one member clears, a
                    # shorter member of that same geometry cannot follow.
                    elif gain <= 1e-12:
                        break
                    if source == "sliding_exact":
                        clears = context.clearance_adapter.connector_clears(
                            candidate)
                    else:
                        clears = _candidate_clears(
                            context, foreign_obstacles, candidate, source,
                            chain.segments[i:j])
                    if not clears:
                        continue
                    if _touches_other_same_net(
                            candidate, outside, net_vias,
                            (chain.points[i], chain.points[j])):
                        continue
                    edges[i].append((j, candidate, True, new_length))
                    break

    # Direction is part of the state: a valid edge may still make a 90-degree
    # corner with the preceding edge.  Existing input-input corners remain a
    # legal fallback; G3 only forbids creating a new one.
    best = [dict() for _ in range(n + 1)]
    previous = {}
    best[0][(None, False)] = (0.0, 0)
    for i in range(n):
        for state, cost in list(best[i].items()):
            prior_direction, prior_changed = state
            for edge in sorted(edges[i], key=lambda item: (item[0], item[3])):
                j, candidate, changed, length = edge
                first_direction, last_direction = _edge_directions(
                    candidate, chain.points[i], chain.points[j])
                if (prior_direction is not None and
                        _right_angle(prior_direction, first_direction) and
                        (prior_changed or changed)):
                    continue
                next_state = (last_direction, changed)
                score = (cost[0] + length, cost[1] + len(candidate))
                current_score = best[j].get(next_state)
                better = (current_score is None or
                          score[0] < current_score[0] - 1e-12 or
                          (abs(score[0] - current_score[0]) <= 1e-12 and
                           score[1] < current_score[1]))
                if better:
                    best[j][next_state] = score
                    previous[(j, next_state)] = (
                        i, state, candidate, changed)

    if not best[n]:
        return None
    selected = []
    cursor = n
    state = min(best[n], key=lambda item: (
        round(best[n][item][0], 12), best[n][item][1]))
    while cursor:
        i, prior_state, candidate, changed = previous[(cursor, state)]
        selected.append((i, cursor, candidate, changed))
        cursor = i
        state = prior_state
    selected.reverse()

    removed = []
    added = []
    for i, j, candidate, changed in selected:
        if changed:
            removed.extend(chain.segments[i:j])
            added.extend(candidate)
    if not removed:
        return None
    old_length = calculate_route_length(removed)
    new_length = calculate_route_length(added)
    gain = old_length - new_length
    if objective == "fewer_segments":
        if abs(gain) > 1e-9 or len(added) >= len(removed):
            return None
    elif gain <= min_gain:
        return None
    # G3's fast grid search is never the final safety authority: every emitted
    # connector is rechecked with the exact KRT smooth semantics.
    if not context.clearance_adapter.connector_clears(added):
        return None
    return removed, added


def shorten_routes(context, results, deadline=None, *, net_ids,
                   objective="shorter", stage="G3"):
    """Run one deterministic dgloss pass, net by net, with fixed vias."""
    changes = GlossChanges()
    strips = []
    added_all = []
    per_net = []
    totals = {"nets_changed": 0, "segments_removed": 0,
              "segments_added": 0, "saved_mm": 0.0,
              "algorithm_ms": 0.0, "per_net": per_net}
    for net_id in net_ids:
        if deadline is not None and perf_counter() >= deadline:
            break
        started = perf_counter()
        net_segments = [s for s in context.pcb_data.segments
                        if s.net_id == net_id]
        net_vias = [v for v in context.pcb_data.vias if v.net_id == net_id]
        before_length = calculate_route_length(net_segments, net_vias,
                                               context.pcb_data)
        foreign = context.foreign_obstacles(net_id)

        removed_net = []
        added_net = []
        for chain in _simple_chains(context.pcb_data, net_id):
            if deadline is not None and perf_counter() >= deadline:
                break
            current = [s for s in context.pcb_data.segments if s.net_id == net_id]
            replacement = _best_chain_replacement(
                context, chain, net_id, foreign, current, net_vias,
                deadline=deadline, objective=objective)
            if replacement is None:
                continue
            removed, added = replacement
            removed_ids = {id(seg) for seg in removed}
            trial = [seg for seg in current if id(seg) not in removed_ids] + added
            before_grade = check_net_connectivity(
                net_id, current, net_vias,
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            after_grade = check_net_connectivity(
                net_id, trial, net_vias,
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            if _connectivity_worse(before_grade, after_grade):
                continue
            gain = (calculate_route_length(
                        current, net_vias, context.pcb_data) -
                    calculate_route_length(
                        trial, net_vias, context.pcb_data))
            if objective == "fewer_segments":
                if abs(gain) > 1e-9 or len(trial) >= len(current):
                    continue
            elif gain <= context.coord.grid_step:
                continue
            context.pcb_data.segments = [
                seg for seg in context.pcb_data.segments
                if id(seg) not in removed_ids] + added
            if hasattr(context.pcb_data, "_foreign_seg_arr_cache"):
                context.pcb_data._foreign_seg_arr_cache = None
            removed_net.extend(removed)
            added_net.extend(added)

        after_segments = [s for s in context.pcb_data.segments
                          if s.net_id == net_id]
        after_length = calculate_route_length(after_segments, net_vias,
                                              context.pcb_data)
        elapsed_ms = (perf_counter() - started) * 1000.0
        per_net.append({"net_id": net_id, "before_mm": before_length,
                        "after_mm": after_length,
                        "saved_mm": max(0.0, before_length - after_length),
                        "algorithm_ms": elapsed_ms})
        totals["algorithm_ms"] += elapsed_ms
        if not removed_net:
            continue

        native_segments, _native_vias = release_result_custody(
            results, removed_net)
        strips.extend(native_segments)
        changes.segments.extend({"old": seg, "stage": stage}
                                for seg in removed_net)
        changes.segments.extend({"new": seg, "stage": stage}
                                for seg in added_net)
        added_all.extend(added_net)
        totals["nets_changed"] += 1
        totals["segments_removed"] += len(removed_net)
        totals["segments_added"] += len(added_net)
        totals["saved_mm"] += before_length - after_length

        # Keep the persistent KRT map authoritative for the following net.
        context.refresh_net_obstacles(net_id)

    totals["saved_mm"] = round(totals["saved_mm"], 4)
    totals["algorithm_ms"] = round(totals["algorithm_ms"], 3)
    return strips, added_all, changes, totals
