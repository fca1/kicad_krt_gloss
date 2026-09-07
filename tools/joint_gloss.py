"""Experimental common length/segment DAG, based on algorithm.py at 9cd6a43.

Static prototype copy keeps production untouched and auditable. No work queue,
no full-pass loop. Equal-length simplifications and shortcuts compete in the
same DAG. G3.5 runs this same engine after vias/pads/nodes may have changed copper.
"""
from collections import defaultdict, Counter
from contextlib import contextmanager
from unittest.mock import patch
from dgloss import pipeline
from dgloss.algorithm import (
    _simple_chains, _candidate_segments, _chamfer_candidate_families,
    _adaptive_chamfer_candidates, _reachable_segment_slides,
    _candidate_clearance, _touches_other_same_net, _shortest_path,
    calculate_route_length, stable_copper_search, stays_in_corridor,
    ReplacementGuard, GlossChanges, release_result_custody, perf_counter)
from dgloss.krt_api import Segment


def simplify_candidate(candidate):
    """Merge consecutive same-direction collinear legs without moving copper.

    No short-leg deletion, no 180-degree fold removal, no coordinate rounding.
    KRT still validates the resulting candidate. The test is relational, so
    rotations/reflections do not change the rule.
    """
    result = []
    for segment in candidate:
        if result:
            previous = result[-1]
            ux, uy = previous.end_x-previous.start_x, previous.end_y-previous.start_y
            vx, vy = segment.end_x-segment.start_x, segment.end_y-segment.start_y
            if ((previous.end_x, previous.end_y) == (segment.start_x, segment.start_y)
                    and (previous.layer, previous.width, previous.net_id) ==
                        (segment.layer, segment.width, segment.net_id)
                    and ux*vy == uy*vx and ux*vx+uy*vy > 0):
                result[-1] = Segment(start_x=previous.start_x, start_y=previous.start_y,
                                     end_x=segment.end_x, end_y=segment.end_y,
                                     layer=segment.layer, width=segment.width,
                                     net_id=segment.net_id)
                continue
        result.append(segment)
    return result


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
            if objective in ("shorter", "joint") and stay_in_corridor:
                # Try progressively longer connectors when the shortest one
                # cannot be reached. A failed deformation is not a barrier
                # that justifies discarding the remaining candidate family.
                families.extend(("chamfer", family) for family in
                                _chamfer_candidate_families(
                                    chain.points[i], chain.points[j], chain.layer,
                                    chain.width, net_id, context.coord.grid_step))
            if objective in ("shorter", "joint"):
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
                    candidate = simplify_candidate(candidate)
                    new_length = calculate_route_length(candidate)
                    gain = old_length - new_length
                    if objective == "fewer_segments":
                        if (len(candidate) == 1 or abs(gain) > 1e-9 or
                                len(candidate) >= j - i):
                            continue
                    elif objective == "joint":
                        if gain < -1e-9 or (gain <= 1e-12 and len(candidate) >= j - i):
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
    elif objective == "joint" and abs(gain) <= 1e-9 and len(added) < len(removed):
        pass
    elif gain <= min_gain:
        return None
    return removed, added


def shorten_routes(context, results, deadline=None, *, net_ids,
                   objective="shorter", stage="G3",
                   include_canonical=True, stay_in_corridor=False, local_only=False):
    """Run one deterministic dgloss pass, net by net, with fixed vias."""
    if not local_only and not stay_in_corridor:
        objective = "joint"
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
        for chain in _simple_chains(
                context.pcb_data, net_id, context.editable_segment_ids):
            if deadline is not None and perf_counter() >= deadline:
                break
            current = [s for s in context.pcb_data.segments if s.net_id == net_id]
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
                from dgloss.local_gloss import local_replacement
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
            elif objective == "joint" and abs(gain) <= 1e-9 and len(added) < len(removed):
                pass
            elif use_local and abs(gain) <= 1e-7 and len(added) < len(removed):
                pass
            elif gain <= (1e-7 if use_local else context.coord.grid_step):
                continue
            context.pcb_data.segments = [
                seg for seg in context.pcb_data.segments
                if id(seg) not in removed_ids] + added
            context.replace_editable_segments(removed, added)
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


@contextmanager
def joint_gloss():
    """Activate only for a single-threaded diagnostic run; restore on exit."""
    stats = Counter()
    def run(*args, **kwargs):
        stats['common_engine_calls'] += 1
        return shorten_routes(*args, **kwargs)
    with patch.object(pipeline, 'shorten_routes', run):
        yield stats
