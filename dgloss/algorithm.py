"""G3: one-pass, fixed-via route-length reduction on KRT's grid."""

from collections import defaultdict, Counter
from dataclasses import dataclass
import math
from .execution import perf_counter
from .topology import ReplacementGuard
from dgloss.krt_api import calculate_route_length
from dgloss.krt_api import _segment_fits_wide
from .changes import GlossChanges, release_result_custody
from .segment_sliding import slide_interval, slide_segment, slide_length_rate
from .corridor import stays_in_corridor
from .krt_clearance import stable_copper_search
from .board_views import board_views
from .topology import (_connectivity_worse)
from .route_geometry import (_pad_holds_point, _candidate_segments, _segments_for_points,
    _connector_families, _chamfer_candidate_families, _chamfer_candidate_at,
    _touches_other_same_net, _edge_directions, _right_angle)
from .route_geometry import _octolinear_points
from .chain_topology import (_Chain, _simple_chains)


@dataclass(frozen=True)
class _ClearanceDecision:
    """Clearance verdict plus exact certification carried by the candidate."""

    clear: bool
    exact_segment_ids: frozenset = frozenset()

    def __bool__(self):
        return self.clear


def _last_positive_chamfer_index(a, b, layer, width, net_id, grid_step,
                                 order, old_length):
    """Find the least-gain useful position without materializing the family."""
    diagonal_max = min(abs(b[0] - a[0]), abs(b[1] - a[1]))
    upper = max(0, int((diagonal_max - 1e-9) // grid_step))
    if upper < 1:
        return 0

    def improves(index):
        candidate = _chamfer_candidate_at(
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


def _adaptive_chamfer_candidates(context, obstacles, a, b, layer, width,
                                 net_id, old_length, deadline=None):
    """Search sampled chamfer positions, five KRT cells at a time.

    The search starts next to the existing geometry and moves toward the
    shortest connector. A grid rejection gets KRT's exact confirmation; a
    confirmed first obstruction ends that family. Only the last five-cell
    interval is refined at the actual KRT grid step.
    """
    stride = 5
    orders = (("x", "d", "y"), ("y", "d", "x"))

    def candidate(index, order):
        return _chamfer_candidate_at(
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
        if deadline is not None and perf_counter() >= deadline:
            return
        last = _last_positive_chamfer_index(
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
            if deadline is not None and perf_counter() >= deadline:
                return
            probe = max(1, best - stride)
            tested = candidate(probe, order)
            if clears(tested):
                best = probe
                continue

            # Move back from the first obstruction one real grid cell at a
            # time. Stop at the first valid point: anything beyond the
            # obstruction belongs to another local basin.
            for index in range(probe + 1, best):
                if deadline is not None and perf_counter() >= deadline:
                    return
                tested = candidate(index, order)
                if clears(tested):
                    best = index
                    break
            break
        yield candidate(best, order)


def _reachable_segment_slides(context, source, outside, net_vias, anchors,
                              deadline=None, max_steps=None):
    """Yield the best locally reachable slide in the shortening direction.

    Geometry is provided by :mod:`segment_sliding`; this function is only G3's
    shortening and reachability policy. The useful direction is walked outward
    from the incumbent and stops at its first sampled same-net or exact-KRT
    obstruction. This sampled search is not a continuous corridor certificate.
    """
    rate = slide_length_rate(*source)
    if rate is None or abs(rate) < 1e-9:
        return
    interval = slide_interval(
        *source, minimum_length=context.coord.grid_step)
    if interval is None:
        return
    old_length = calculate_route_length(source)
    step = context.coord.grid_step
    span_limit = max(old_length, step)

    for sign in ((-1,) if rate > 0.0 else (1,)):
        bound = interval.maximum if sign > 0 else -interval.minimum
        if math.isinf(bound):
            bound = span_limit
        bound = min(bound, span_limit)
        count = max(0, int((bound + 1e-9) // step))
        if max_steps is not None:
            count = min(max_steps, count)  # Explicit diagnostic caller only.
        best = None
        for index in range(1, count + 1):
            if deadline is not None and perf_counter() >= deadline:
                break
            candidate = slide_segment(
                *source, sign * index * step, minimum_length=step)
            if candidate is None:
                break
            segments = list(candidate.segments)
            if (_touches_other_same_net(
                    segments, outside, net_vias, anchors) or
                    not context.clearance_adapter.connector_clears(segments)):
                break
            if old_length - candidate.after_length > step + 1e-12:
                best = segments
        if best is not None:
            yield best


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


def _candidate_clearance(context, obstacles, segments, source,
                         source_segments=(), *, defer_exact=False):
    """Geometry-first enumeration; a raster rejection is not a collision.

    Deferred callers must certify their chosen candidates with the geometric
    adapter. No family is discarded solely because a grid cell is blocked.
    """
    if not _candidate_geometry_valid(context, segments):
        return _ClearanceDecision(False)
    if defer_exact:
        return _ClearanceDecision(True)
    clear = context.clearance_adapter.connector_clears(segments)
    return _ClearanceDecision(
        clear, frozenset(map(id, segments)) if clear else frozenset())


def _candidate_clears(context, obstacles, segments, source,
                      source_segments=()):
    """Compatibility boolean wrapper around the transported decision."""
    return bool(_candidate_clearance(
        context, obstacles, segments, source, source_segments))


def _candidate_geometry_valid(context, segments):
    """Keep mandatory, cheap geometry guards ahead of clearance policy."""
    return bool(segments) and not any(
        calculate_route_length([segment]) < context.coord.grid_step - 1e-9 or
        not _octolinear_points((segment.start_x, segment.start_y),
                               (segment.end_x, segment.end_y))
        for segment in segments)


def _shortest_path(edges, points, excluded):
    """Select the best G3 DAG path, ignoring exact-KRT rejected edges."""
    n = len(points) - 1
    best = [dict() for _ in range(n + 1)]
    previous = {}
    best[0][(None, False)] = (0.0, 0)
    for i in range(n):
        for state, cost in list(best[i].items()):
            prior_direction, prior_changed = state
            for edge in sorted(edges[i], key=lambda item: (item[0], item[3])):
                j, candidate, changed, length, edge_id = edge
                if edge_id in excluded:
                    continue
                first_direction, last_direction = _edge_directions(
                    candidate, points[i], points[j])
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
                    previous[(j, next_state)] = (i, state, edge)

    if not best[n]:
        return []
    selected = []
    cursor = n
    state = min(best[n], key=lambda item: (
        round(best[n][item][0], 12), best[n][item][1]))
    while cursor:
        i, prior_state, edge = previous[(cursor, state)]
        selected.append((i, edge))
        cursor = i
        state = prior_state
    selected.reverse()
    return selected


@stable_copper_search
def _best_chain_replacement(context, chain, net_id, foreign_obstacles,
                            net_segments, net_vias, deadline=None,
                            objective="shorter", include_canonical=True,
                            stay_in_corridor=False, accept_replacement=None):
    """Shortest valid path through a chain's ordered vertices (DAG dynamic program)."""
    n = len(chain.segments)
    span_ids = {id(seg) for seg in chain.segments}
    outside = [seg for seg in net_segments if id(seg) not in span_ids]
    edges = defaultdict(list)

    # Keeping an original edge is always a valid option.
    for i, seg in enumerate(chain.segments):
        edges[i].append((i + 1, [seg], False,
                         calculate_route_length([seg]), None))

    min_gain = context.coord.grid_step
    next_edge_id = 0
    next_family_id = 0
    family_edges = {}
    edge_families = {}
    edge_candidates = {}
    edge_spans = {}
    edge_source_points = {}

    for i in range(n - 1):
        if deadline is not None and perf_counter() >= deadline:
            break
        for j in range(i + 2, n + 1):
            if deadline is not None and perf_counter() >= deadline:
                break
            old_length = calculate_route_length(chain.segments[i:j])
            families = []
            if include_canonical:
                families.append(("canonical", _candidate_segments(
                    chain.points[i], chain.points[j], chain.layer,
                    chain.width, net_id)))
            if objective == "shorter" and stay_in_corridor:
                # Try progressively longer connectors when the shortest one
                # cannot be reached. A failed deformation is not a barrier
                # that justifies discarding the remaining candidate family.
                families.extend(("chamfer", family) for family in
                                _chamfer_candidate_families(
                                    chain.points[i], chain.points[j], chain.layer,
                                    chain.width, net_id, context.coord.grid_step))
            if objective == "shorter":
                families.append(("chamfer_exact", _adaptive_chamfer_candidates(
                    context, foreign_obstacles, chain.points[i], chain.points[j],
                    chain.layer, chain.width, net_id, old_length, deadline)))
                if j == i + 3:
                    slides = _reachable_segment_slides(
                        context, tuple(chain.segments[i:j]), outside, net_vias,
                        (chain.points[i], chain.points[j]), deadline=deadline)
                    for candidate in slides:
                        families.append(("segment_slide_exact", iter((candidate,))))
            for _source, family in families:
                if deadline is not None and perf_counter() >= deadline:
                    break
                family_id = next_family_id
                next_family_id += 1
                family_edges[family_id] = []
                for candidate in family:
                    if deadline is not None and perf_counter() >= deadline:
                        break
                    new_length = calculate_route_length(candidate)
                    gain = old_length - new_length
                    if objective == "fewer_segments":
                        if (len(candidate) == 1 or abs(gain) > 1e-9 or
                                len(candidate) >= j - i):
                            continue
                    elif gain <= 1e-12:
                        break
                    if not _candidate_clearance(
                            context, foreign_obstacles, candidate, _source,
                            chain.segments[i:j], defer_exact=True):
                        continue
                    if _touches_other_same_net(
                            candidate, outside, net_vias,
                            (chain.points[i], chain.points[j])):
                        continue
                    edge_id = next_edge_id
                    next_edge_id += 1
                    edges[i].append(
                        (j, candidate, True, new_length, edge_id))
                    family_edges[family_id].append(edge_id)
                    edge_families[edge_id] = family_id
                    edge_candidates[edge_id] = candidate
                    edge_spans[edge_id] = (i, j)
                    if stay_in_corridor:
                        edge_source_points[edge_id] = chain.points[i:j + 1]

    # Exact KRT geometry remains authoritative. When an edge wins, validate its
    # family predecessors in generator order. The first exact-valid candidate
    # becomes that family's sole option, exactly matching the eager policy.
    excluded = set()
    exact_status = {}
    while True:
        if deadline is not None and perf_counter() >= deadline:
            return None
        selected = _shortest_path(edges, chain.points, excluded)
        if not selected:
            return None
        changed_selection = False
        for _i, edge in selected:
            edge_id = edge[4]
            if not edge[2]:
                continue
            family = family_edges[edge_families[edge_id]]
            selected_rank = family.index(edge_id)
            first_valid = None
            for preceding_id in family[:selected_rank + 1]:
                if deadline is not None and perf_counter() >= deadline:
                    return None
                if preceding_id not in exact_status:
                    exact_status[preceding_id] = (
                        context.clearance_adapter.connector_clears(
                            edge_candidates[preceding_id]) and
                        (not stay_in_corridor or stays_in_corridor(
                            context, edge_source_points[preceding_id],
                            edge_candidates[preceding_id], deadline)))
                    if exact_status[preceding_id] and accept_replacement:
                        # Certify this shortcut, not only the final DAG winner.
                        # A rejected shortcut leaves the other spans available.
                        span = edge_spans[preceding_id]
                        exact_status[preceding_id] = accept_replacement(
                            chain.segments[span[0]:span[1]],
                            edge_candidates[preceding_id])
                if exact_status[preceding_id]:
                    first_valid = preceding_id
                    break
                excluded.add(preceding_id)
            if first_valid is None:
                changed_selection = True
                continue
            # Eager G3 stops this family at its first exact-valid candidate.
            first_rank = family.index(first_valid)
            excluded.update(family[first_rank + 1:])
            if first_valid != edge_id:
                changed_selection = True
        if not changed_selection:
            removed = [segment for i, edge in selected if edge[2]
                       for segment in chain.segments[i:edge[0]]]
            added = [segment for _i, edge in selected if edge[2]
                     for segment in edge[1]]
            if removed and accept_replacement and not accept_replacement(removed, added):
                # Individually safe shortcuts may together remove two alternate
                # zone contacts. Reject this combination and keep searching.
                changed = [(i, edge) for i, edge in selected if edge[2]]
                i, edge = min(changed, key=lambda item:
                              calculate_route_length(chain.segments[item[0]:item[1][0]])
                              - item[1][3])
                excluded.add(edge[4])
                exact_status[edge[4]] = False
                continue
            break

    removed = []
    added = []
    for i, edge in selected:
        j, candidate, changed, _length, _edge_id = edge
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
    return removed, added


def _scheduled_chains(pcb, net, allowed_segment_ids=None):
    from .auto_gloss import revisit_chains
    return revisit_chains(_simple_chains, pcb, net, allowed_segment_ids, Counter())


def shorten_routes(context, results, deadline=None, *, net_ids,
                   objective="shorter", stage="G3",
                   include_canonical=True, stay_in_corridor=False, local_only=False):
    """Reduce with fixed vias, revisiting changed complete chains locally."""
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
        net_segments = board_views(context.pcb_data).segments(net_id)
        net_vias = board_views(context.pcb_data).vias(net_id)
        before_length = calculate_route_length(net_segments, net_vias,
                                               context.pcb_data)
        foreign = context.foreign_obstacles(net_id)

        removed_net = []
        added_net = []
        for chain in _scheduled_chains(
                context.pcb_data, net_id, context.editable_segment_ids):
            if deadline is not None and perf_counter() >= deadline:
                break
            current = board_views(context.pcb_data).segments(net_id)
            cache = getattr(context, "search_cache", None)
            cache_key = None
            if cache is not None:
                cache_key, reused = cache.token(
                    "tracks", net_id, chain.segments,
                    (objective, include_canonical, stay_in_corridor, local_only))
                if reused:
                    continue
            use_local = objective == "shorter" and (stay_in_corridor or local_only)
            if use_local:
                from .local_gloss import local_replacement
                replacement = local_replacement(
                    context, chain, net_id, current, net_vias, deadline)
            else:
                replacement = _best_chain_replacement(
                    context, chain, net_id, foreign, current, net_vias,
                    deadline=deadline, objective=objective,
                    include_canonical=include_canonical,
                    stay_in_corridor=stay_in_corridor,
                    accept_replacement=ReplacementGuard(
                        context.pcb_data, net_id, current, net_vias))
            if replacement is None:
                if cache is not None and (deadline is None or perf_counter() < deadline):
                    cache.remember_failure(cache_key, chain.segments)
                continue
            removed, added = replacement
            removed_ids = {id(seg) for seg in removed}
            trial = [seg for seg in current if id(seg) not in removed_ids] + added
            gain = (calculate_route_length(
                        current, net_vias, context.pcb_data) -
                    calculate_route_length(
                        trial, net_vias, context.pcb_data))
            if objective == "fewer_segments":
                if abs(gain) > 1e-9 or len(trial) >= len(current):
                    continue
            elif use_local and abs(gain) <= 1e-7 and len(added) < len(removed):
                pass
            elif gain <= (1e-7 if use_local else context.coord.grid_step):
                continue
            context.apply_replacement(removed, added)
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

        # A chain can be edited several times before result custody is emitted.
        # Keep only the stage's input removals and its surviving output copper.
        input_ids = {id(segment) for segment in net_segments}
        final_ids = {id(segment) for segment in after_segments}
        removed_net = [segment for segment in removed_net if id(segment) in input_ids]
        added_net = [segment for segment in added_net if id(segment) in final_ids]
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
