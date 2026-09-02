"""Public KRT integration points for the final gloss."""

import math
from dataclasses import dataclass, field
from time import perf_counter

from check_connected import check_net_connectivity
from cleanup_pipeline import _smooth_skip_net_ids
from geometry_utils import UnionFind
from net_queries import calculate_route_length
from pcb_modification import merge_collinear_segments, smooth_octolinear_chains

from .algorithm import _connectivity_worse, shorten_routes
from .changes import GlossChanges
from .config import GlossConfig
from .context import build_gloss_context
from .pad_terminals import optimize_pad_terminals
from .passes import run_multinet_passes
from .sliding_nodes import slide_t_nodes
from .stats import GlossStats
from .via_mobile import move_mobile_vias, refine_mobile_vias


@dataclass
class GlossOutcome:
    input_strip_segments: list = field(default_factory=list)
    input_strip_vias: list = field(default_factory=list)
    changes: dict = field(default_factory=lambda: {"segments": [], "vias": []})
    stats: dict = field(default_factory=dict)


def _result_snapshot(results):
    return [(result, list(result.get("new_segments") or []),
             list(result.get("new_vias") or [])) for result in results]


def _restore(results, count, snapshot, pcb_data, segments, vias):
    pcb_data.segments = segments
    pcb_data.vias = vias
    del results[count:]
    for result, result_segments, result_vias in snapshot:
        result["new_segments"] = result_segments
        result["new_vias"] = result_vias
    if hasattr(pcb_data, "_foreign_seg_arr_cache"):
        pcb_data._foreign_seg_arr_cache = None


def _grade(pcb_data, net_id):
    return check_net_connectivity(
        net_id,
        [segment for segment in pcb_data.segments if segment.net_id == net_id],
        [via for via in pcb_data.vias if via.net_id == net_id],
        pcb_data.pads_by_net.get(net_id, []), [], pcb_data=pcb_data)


def _g5_grade(pcb_data, net_id):
    zones = [zone for zone in (getattr(pcb_data, "zones", None) or [])
             if zone.net_id == net_id]
    return check_net_connectivity(
        net_id,
        [segment for segment in pcb_data.segments if segment.net_id == net_id],
        [via for via in pcb_data.vias if via.net_id == net_id],
        pcb_data.pads_by_net.get(net_id, []), zones, pcb_data=pcb_data,
        return_graph=True)


def _terminal_partition(grade):
    """Normalize KRT terminal components so graph ids can be compared."""
    graph = grade.get("graph") or {}
    if graph:
        union = UnionFind()
        for first, second in graph.get("edges", ()):
            union.union(first, second)
        groups = {}
        terminals = [
            (("pad", index), point)
            for index, point in (graph.get("pad_index_repr") or {}).items()
        ] + [
            (("zone", index), point)
            for index, point in (graph.get("zone_index_repr") or {}).items()
        ]
        for terminal, point in terminals:
            groups.setdefault(union.find(point), set()).add(terminal)
        return frozenset(frozenset(group) for group in groups.values())

    # Small synthetic callers may provide only check_net_connectivity's
    # public pad_components summary.
    groups = {}
    for pad, component in (grade.get("pad_components") or {}).items():
        groups.setdefault(component, set()).add(pad)
    return frozenset(frozenset(group) for group in groups.values())


def _append_result(results, cleanup, added_segments, added_vias, changes):
    if changes:
        results.append({
            "new_segments": added_segments, "new_vias": added_vias,
            "cleanup": cleanup,
            "track_gloss_changes": changes.as_dict(),
        })


def _empty_via_stats():
    return {"vias_moved": 0, "saved_mm": 0.0, "net_ids_changed": set(),
            "algorithm_ms": 0.0, "segment_strips": [],
            "added_segments": []}


def _run_g3_5_pass(results, pcb_data, config, selected, net_ids, deadline, *,
                    emit_log):
    """Execute G3--G3.5 directly for the supplied complete KRT net list."""
    # ``None`` is the public "all routed nets" sentinel.  At this internal
    # boundary an empty list is already a resolved scope and must stay empty:
    # turning it back into None would unexpectedly gloss every routed net.
    context = build_gloss_context(pcb_data, config, net_ids=net_ids)
    before_length = calculate_route_length(pcb_data.segments)
    before_grades = {net_id: _grade(pcb_data, net_id)
                     for net_id in context.net_ids}
    changes = GlossChanges()
    stage_stats = GlossStats(
        budget_seconds=max(0.0, deadline - perf_counter()), emit=emit_log)

    def available(enabled):
        expired = perf_counter() >= deadline
        stage_stats.budget_expired = stage_stats.budget_expired or expired
        return enabled and not expired, expired

    strips, added, g3_changes, g3 = shorten_routes(
        context, results, deadline=deadline)
    _append_result(results, "track_gloss_g3", added, [], g3_changes)
    changes.segments.extend(g3_changes.segments)
    changes.vias.extend(g3_changes.vias)
    stage_stats.record("G3", changes=g3["nets_changed"],
                       saved_mm=g3["saved_mm"],
                       elapsed_ms=g3["algorithm_ms"],
                       label="nets améliorés")

    run, expired = available(selected.enable_g3_1)
    via_strips, added_vias, via_changes, via = \
        move_mobile_vias(context, results, deadline=deadline) \
        if run else ([], [], GlossChanges(), _empty_via_stats())
    _append_result(results, "track_gloss_g3_1", via["added_segments"],
                   added_vias, via_changes)
    changes.vias.extend(via_changes.vias)
    changes.segments.extend(via_changes.segments)
    stage_stats.record("G3.1", enabled=selected.enable_g3_1,
                       skipped_budget=expired and selected.enable_g3_1,
                       changes=via["vias_moved"], saved_mm=via["saved_mm"],
                       elapsed_ms=via["algorithm_ms"], label="vias déplacés")

    run, expired = available(selected.enable_g3_2)
    pad_strips, pad_added, pad_changes, pad = \
        optimize_pad_terminals(context, results, deadline=deadline) \
        if run else ([], [], GlossChanges(), {
            "pads_changed": 0, "saved_mm": 0.0,
            "net_ids_changed": set(), "algorithm_ms": 0.0})
    _append_result(results, "track_gloss_g3_2", pad_added, [], pad_changes)
    changes.segments.extend(pad_changes.segments)
    stage_stats.record("G3.2", enabled=selected.enable_g3_2,
                       skipped_budget=expired and selected.enable_g3_2,
                       changes=pad["pads_changed"], saved_mm=pad["saved_mm"],
                       elapsed_ms=pad["algorithm_ms"], label="pads optimisés")

    run, expired = available(selected.enable_g3_3)
    node_strips, node_added, node_changes, node = \
        slide_t_nodes(
            context, results, deadline=deadline,
            allow_noncollinear=selected.enable_noncollinear_t_rails) \
        if run else ([], [], GlossChanges(), {
            "t_branches_slid": 0, "saved_mm": 0.0,
            "noncollinear_t_slid": 0, "right_angles_cleaned": 0,
            "net_ids_changed": set(), "algorithm_ms": 0.0})
    _append_result(results, "track_gloss_g3_3", node_added, [], node_changes)
    changes.segments.extend(node_changes.segments)
    stage_stats.record("G3.3", enabled=selected.enable_g3_3,
                       skipped_budget=expired and selected.enable_g3_3,
                       changes=node["t_branches_slid"],
                       saved_mm=node["saved_mm"],
                       elapsed_ms=node["algorithm_ms"],
                       label="branches en T déplacées")
    if emit_log and node["noncollinear_t_slid"]:
        print("Track Gloss G3.3 non-collinear variant: "
              f"{node['noncollinear_t_slid']} T sans rail colinéaire, "
              f"{node['right_angles_cleaned']} coudes à 90° nettoyés")

    run, expired = available(selected.enable_g3_4)
    refine_strips, refine_vias, refine_changes, refine = \
        refine_mobile_vias(context, results, deadline=deadline) \
        if run else ([], [], GlossChanges(), _empty_via_stats())
    _append_result(results, "track_gloss_g3_4", refine["added_segments"],
                   refine_vias, refine_changes)
    changes.vias.extend(refine_changes.vias)
    changes.segments.extend(refine_changes.segments)
    stage_stats.record("G3.4", enabled=selected.enable_g3_4,
                       skipped_budget=expired and selected.enable_g3_4,
                       changes=refine["vias_moved"],
                       saved_mm=refine["saved_mm"],
                       elapsed_ms=refine["algorithm_ms"],
                       label="vias affinés")

    run, expired = available(True)
    equal_strips, equal_added, equal_changes, equal = \
        shorten_routes(
            context, results, deadline=deadline,
            objective="fewer_segments", stage="G3.5") \
        if run else ([], [], GlossChanges(), {
            "nets_changed": 0, "segments_removed": 0,
            "segments_added": 0, "saved_mm": 0.0,
            "algorithm_ms": 0.0, "per_net": []})
    _append_result(results, "track_gloss_g3_5_equal_length",
                   equal_added, [], equal_changes)
    changes.segments.extend(equal_changes.segments)
    stage_stats.record(
        "G3.5 equal length", skipped_budget=expired,
        changes=equal["segments_removed"] - equal["segments_added"],
        saved_mm=0.0, elapsed_ms=equal["algorithm_ms"],
        label="segments supprimés à longueur égale")

    run, expired = available(True)
    merge_before = list(pcb_data.segments)
    merge_started = perf_counter()
    if run:
        merged_count, merged_nets, merge_strips, merge_added, merge = \
            merge_collinear_segments(results, pcb_data, set(context.net_ids))
    else:
        merged_count, merged_nets = 0, 0
        merge_strips, merge_added = [], []
        merge = {"joints": 0, "segs_removed": 0, "segs_added": 0,
                 "nets_skipped_large": 0}
    merge_ms = (perf_counter() - merge_started) * 1000.0
    final_segment_ids = {id(segment) for segment in pcb_data.segments}
    merge_removed = [segment for segment in merge_before
                     if id(segment) not in final_segment_ids]
    merge_changes = GlossChanges(
        segments=([{"old": segment, "stage": "G3.5"}
                   for segment in merge_removed] +
                  [{"new": segment, "stage": "G3.5",
                    "geometry_preserving": True}
                   for segment in merge_added]))
    changes.segments.extend(merge_changes.segments)
    stage_stats.record(
        "G3.5 segments", skipped_budget=expired,
        changes=merge.get("joints", 0), saved_mm=0.0,
        elapsed_ms=merge_ms, label="jonctions colinéaires supprimées")

    after_length = _validate_final(
        context, before_grades, before_length, changes)
    changed_net_ids = {row["net_id"] for row in g3.get("per_net", [])
                       if row.get("saved_mm", 0.0) > 0.0}
    for row in (via, pad, node, refine):
        changed_net_ids.update(row["net_ids_changed"])
    changed_net_ids.update(
        entry["old"].net_id for entry in equal_changes.segments
        if "old" in entry)
    changed_net_ids.update(segment.net_id for segment in merge_removed)

    return {
        "context": context, "changes": changes,
        "segment_strips": (strips + via["segment_strips"] + pad_strips +
                           node_strips + refine["segment_strips"] +
                           equal_strips + merge_strips),
        "via_strips": via_strips + refine_strips,
        "stage_stats": stage_stats, "changed_net_ids": changed_net_ids,
        "before_length": before_length, "after_length": after_length,
        "g3": g3, "via": via, "pad": pad, "node": node,
        "refine": refine, "equal": equal,
        "merged_count": merged_count, "merged_nets": merged_nets,
        "merge": merge, "merge_ms": merge_ms,
    }


def _final_visual_changes(baseline_segments, baseline_vias, pcb_data,
                          history):
    """Describe only the post-smooth to final G4 delta, without intermediates."""
    final_segment_ids = {id(segment) for segment in pcb_data.segments}
    baseline_segment_ids = {id(segment) for segment in baseline_segments}
    segments = [
        {"old": segment, "stage": "G4"}
        for segment in baseline_segments if id(segment) not in final_segment_ids]
    segments.extend(
        {"new": segment, "stage": "G4"}
        for segment in pcb_data.segments
        if id(segment) not in baseline_segment_ids)

    roots = {}
    for entry in history.vias:
        old, new = entry.get("old"), entry.get("new")
        if old is None or new is None:
            continue
        root = roots.pop(id(old), old)
        roots[id(new)] = root
    final_via_ids = {id(via) for via in pcb_data.vias}
    vias = [{"old": old, "new": via, "stage": "G4"}
            for via in pcb_data.vias
            if id(via) in roots and id(via) in final_via_ids
            for old in [roots[id(via)]]]
    return GlossChanges(segments=segments, vias=vias)


def _validate_final(context, before_grades, before_length, changes):
    """G3.5 safety gate retained by each internal G4 net call."""
    after_length = calculate_route_length(context.pcb_data.segments)
    if after_length > before_length + 1e-9:
        raise RuntimeError("G3.5 final length increased")
    for net_id, before in before_grades.items():
        after = _grade(context.pcb_data, net_id)
        if _connectivity_worse(before, after):
            raise RuntimeError(f"G3.5 connectivity regression on net {net_id}")
    final_segment_ids = {id(segment)
                         for segment in context.pcb_data.segments}
    for entry in changes.segments:
        segment = entry.get("new")
        if segment is None or id(segment) not in final_segment_ids:
            continue
        if entry.get("geometry_preserving"):
            continue
        dx = abs(segment.end_x - segment.start_x)
        dy = abs(segment.end_y - segment.start_y)
        length = math.hypot(dx, dy)
        # Imported pad/track coordinates can differ by a few 1e-5 mm. This is
        # only a KRT-resolution classification tolerance, never a search step.
        tolerance = max(1e-7, context.coord.grid_step / 100.0)
        if not (dx <= tolerance or dy <= tolerance or
                abs(dx - dy) <= tolerance):
            raise RuntimeError("G3.5 produced non-octolinear copper")
        if length < context.coord.grid_step - 1e-9:
            raise RuntimeError("G3.5 produced a micro-segment")
    return after_length


def _certify_g5_copper(context, before_grades, changes):
    """Recheck final changed copper with KRT; no geometry is generated here."""
    for net_id, before in before_grades.items():
        after = _g5_grade(context.pcb_data, net_id)
        if _terminal_partition(before) != _terminal_partition(after):
            raise RuntimeError(f"G5 topology changed on net {net_id}")

    final_segment_ids = {id(segment) for segment in context.pcb_data.segments}
    final_via_ids = {id(via) for via in context.pcb_data.vias}
    segment_ids = set()
    via_ids = set()
    preserved_segments = 0

    for entry in changes.segments:
        segment = entry.get("new")
        if (segment is None or id(segment) not in final_segment_ids or
                id(segment) in segment_ids):
            continue
        segment_ids.add(id(segment))
        if entry.get("geometry_preserving"):
            preserved_segments += 1
            continue
        if not context.clearance_adapter.segment_clears(segment):
            raise RuntimeError(
                f"G5 final copper clearance regression on net {segment.net_id}")

    via_attributes = ("size", "drill", "layers", "net_id", "free", "locked",
                      "tenting_attrs")
    for entry in changes.vias:
        old, via = entry.get("old"), entry.get("new")
        if (old is None or via is None or id(via) not in final_via_ids or
                id(via) in via_ids):
            continue
        via_ids.add(id(via))
        if any(getattr(old, name, None) != getattr(via, name, None)
               for name in via_attributes):
            raise RuntimeError(
                f"G5 moved-via attributes changed on net {via.net_id}")
        if not context.clearance_adapter.via_clears(via, ignored_via=via):
            raise RuntimeError(
                f"G5 final via clearance regression on net {via.net_id}")

    return {
        "segments_certified": len(segment_ids) - preserved_segments,
        "segments_geometry_preserved": preserved_segments,
        "vias_certified": len(via_ids),
    }


def run_final_gloss(results, pcb_data, config, gloss_config=None, *,
                    net_ids=None):
    """Plugin wrapper: run the last KRT smooth, then the post-smooth G0 API."""
    original_segments = list(pcb_data.segments)
    original_vias = list(pcb_data.vias)
    original_count = len(results)
    original_results = _result_snapshot(results)
    try:
        started = perf_counter()
        present_net_ids = {segment.net_id for segment in pcb_data.segments
                           if segment.net_id}
        scope_net_ids = list(net_ids or ())
        requested_net_ids = set(scope_net_ids)
        smooth_net_ids = sorted(
            present_net_ids if not requested_net_ids else
            present_net_ids.intersection(requested_net_ids))
        _count, _nets, strips, _added, krt_stats = smooth_octolinear_chains(
            results, pcb_data, smooth_net_ids,
            clearance=config.clearance,
            net_clearances=getattr(config, "net_clearances", None),
            board_edge_clearance=config.board_edge_clearance,
            config=config, skip_net_ids=_smooth_skip_net_ids(pcb_data),
            min_gain=config.grid_step)
        krt_ms = (perf_counter() - started) * 1000.0
        return run_post_smooth_gloss(
            results, pcb_data, config, gloss_config=gloss_config,
            net_ids=scope_net_ids, krt_strips=strips, krt_stats=krt_stats,
            krt_ms=krt_ms)
    except Exception as exc:
        _restore(results, original_count, original_results, pcb_data,
                 original_segments, original_vias)
        print(f"Track Gloss skipped; input preserved: {exc}")
        return GlossOutcome(stats={"nets_changed": 0, "saved_mm": 0.0,
                                   "gloss_errors": 1})


def run_post_smooth_gloss(results, pcb_data, config, gloss_config=None, *,
                          net_ids=None, krt_strips=None, krt_stats=None,
                          krt_ms=0.0, _emit_log=True):
    """G0 API for a caller that already owns the final KRT smooth result."""
    baseline_segments = list(pcb_data.segments)
    baseline_vias = list(pcb_data.vias)
    baseline_count = len(results)
    baseline_results = _result_snapshot(results)
    krt_strips = list(krt_strips or [])
    krt_stats = krt_stats or {}
    selected = GlossConfig.from_value(
        gloss_config if gloss_config is not None
        else getattr(config, "gloss_config", None))
    gloss_stats = GlossStats(budget_seconds=selected.budget_seconds,
                             emit=_emit_log)
    started = perf_counter()
    deadline = started + max(0.0, selected.budget_seconds)

    try:
        present_net_ids = {segment.net_id for segment in pcb_data.segments
                           if segment.net_id}
        requested_net_ids = set(net_ids or ())
        scope_net_ids = sorted(
            present_net_ids if not requested_net_ids else
            present_net_ids.intersection(requested_net_ids))
        board_before_length = calculate_route_length(pcb_data.segments)
        before_length = calculate_route_length([
            segment for segment in pcb_data.segments
            if segment.net_id in scope_net_ids])
        before_grades = {net_id: _grade(pcb_data, net_id)
                         for net_id in scope_net_ids}
        g5_before_grades = {net_id: _g5_grade(pcb_data, net_id)
                            for net_id in scope_net_ids}
        initial = _run_g3_5_pass(
            results, pcb_data, config, selected, scope_net_ids, deadline,
            emit_log=_emit_log)
        context = initial["context"]
        changes = initial["changes"]
        gloss_stats = initial["stage_stats"]
        g3, via, pad = initial["g3"], initial["via"], initial["pad"]
        node, refine = initial["node"], initial["refine"]
        equal = initial["equal"]
        merged_count, merged_nets = (initial["merged_count"],
                                     initial["merged_nets"])
        merge, merge_ms = initial["merge"], initial["merge_ms"]

        def available(enabled):
            expired = perf_counter() >= deadline
            gloss_stats.budget_expired = gloss_stats.budget_expired or expired
            return enabled and not expired, expired

        run, expired = available(selected.enable_multipasses)
        g4 = run_multinet_passes(
            pcb_data, config, selected, list(context.net_ids), results,
            deadline, _run_g3_5_pass) if run else {
                "segment_strips": [], "via_strips": [],
                "changes": GlossChanges(), "passes": [],
                "passes_completed": 0, "transformations": 0,
                "segment_reduction": 0,
                "net_ids_changed": set(), "saved_mm": 0.0,
                "algorithm_ms": 0.0,
                "stop_reason": "budget" if expired else "disabled",
            }
        changes.segments.extend(g4["changes"].segments)
        changes.vias.extend(g4["changes"].vias)
        gloss_stats.record(
            "G4", enabled=selected.enable_multipasses,
            skipped_budget=expired and selected.enable_multipasses,
            changes=g4["transformations"], saved_mm=g4["saved_mm"],
            elapsed_ms=g4["algorithm_ms"], label="transformations multinet")

        _validate_final(context, before_grades, board_before_length, changes)
        after_length = calculate_route_length([
            segment for segment in pcb_data.segments
            if segment.net_id in scope_net_ids])
        g5_started = perf_counter()
        g5 = _certify_g5_copper(context, g5_before_grades, changes)
        g5_ms = (perf_counter() - g5_started) * 1000.0
        gloss_stats.record(
            "G5", changes=(g5["segments_certified"] +
                           g5["vias_certified"]),
            saved_mm=0.0, elapsed_ms=g5_ms,
            label="objets finaux certifiés")
        changed_net_ids = set(initial["changed_net_ids"])
        changed_net_ids.update(g4["net_ids_changed"])
        elapsed_ms = (perf_counter() - started) * 1000.0
        gloss_stats.budget_expired = (gloss_stats.budget_expired or
                                      perf_counter() >= deadline)
        total_saved = round(before_length - after_length, 4)
        stats = dict(g3)
        stats.update({
            "config": selected.as_dict(), "gloss": gloss_stats.as_dict(),
            "nets_processed": len(context.net_ids),
            "nets_changed": len(changed_net_ids), "saved_mm": total_saved,
            "segment_changes": len(changes.segments),
            "via_changes": len(changes.vias),
            "before_mm": round(before_length, 4),
            "after_mm": round(after_length, 4),
            "total_ms": round(elapsed_ms, 3),
            "krt_baseline_ms": round(krt_ms, 3),
            "krt_baseline_saved_mm": krt_stats.get("saved_mm", 0.0),
            "vias_moved": via["vias_moved"],
            "via_algorithm_ms": via["algorithm_ms"],
            "pads_changed": pad["pads_changed"],
            "pad_algorithm_ms": pad["algorithm_ms"],
            "pad_saved_mm": pad["saved_mm"],
            "t_branches_slid": node["t_branches_slid"],
            "noncollinear_t_slid": node["noncollinear_t_slid"],
            "right_angles_cleaned": node["right_angles_cleaned"],
            "node_algorithm_ms": node["algorithm_ms"],
            "node_saved_mm": node["saved_mm"],
            "vias_refined": refine["vias_moved"],
            "refine_via_algorithm_ms": refine["algorithm_ms"],
            "refine_via_saved_mm": refine["saved_mm"],
            "equal_length_nets_changed": equal["nets_changed"],
            "equal_length_segments_removed": equal["segments_removed"],
            "equal_length_segments_added": equal["segments_added"],
            "equal_length_segment_reduction": (
                equal["segments_removed"] - equal["segments_added"]),
            "equal_length_algorithm_ms": equal["algorithm_ms"],
            "segments_merged": merged_count,
            "merge_nets_changed": merged_nets,
            "merge_joints": merge.get("joints", 0),
            "merge_segments_removed": merge.get("segs_removed", 0),
            "merge_segments_added": merge.get("segs_added", 0),
            "merge_nets_skipped_large": merge.get(
                "nets_skipped_large", 0),
            "merge_algorithm_ms": round(merge_ms, 3),
            "g4_passes": g4["passes"],
            "g4_passes_completed": g4["passes_completed"],
            "g4_transformations": g4["transformations"],
            "g4_segment_reduction": g4["segment_reduction"],
            "g4_saved_mm": g4["saved_mm"],
            "g4_algorithm_ms": g4["algorithm_ms"],
            "g4_stop_reason": g4["stop_reason"],
            "g5_segments_certified": g5["segments_certified"],
            "g5_segments_geometry_preserved": (
                g5["segments_geometry_preserved"]),
            "g5_vias_certified": g5["vias_certified"],
            "g5_algorithm_ms": round(g5_ms, 3),
            "g5_valid": True,
            "connectivity_regressions": 0,
        })
        if _emit_log:
            print(f"Track Gloss G3.5: {len(context.net_ids)} nets parcourus, "
                  f"{len(changed_net_ids)} améliorés, -{total_saved:.4f} mm, "
                  f"{elapsed_ms:.1f} ms")
        # Since G4, visualisation is always the single final delta on User.1.
        # The multipass switch controls optimisation only; it must never bring
        # back the historical G3--G3.5 overlays on User.2 through User.6.
        final_visual = _final_visual_changes(
            baseline_segments, baseline_vias, pcb_data, changes)
        for result in results[baseline_count:]:
            result.pop("track_gloss_changes", None)
        if final_visual:
            results.append({
                "new_segments": [], "new_vias": [],
                "cleanup": "track_gloss_g4_visualization",
                "track_gloss_changes": final_visual.as_dict(),
            })
        return GlossOutcome(
            input_strip_segments=(krt_strips +
                                  initial["segment_strips"] +
                                  g4["segment_strips"]),
            input_strip_vias=(initial["via_strips"] +
                              g4["via_strips"]),
            changes=changes.as_dict(), stats=stats)
    except Exception as exc:
        _restore(results, baseline_count, baseline_results, pcb_data,
                 baseline_segments, baseline_vias)
        if _emit_log:
            print(f"Track Gloss skipped; KRT result preserved: {exc}")
        return GlossOutcome(
            input_strip_segments=krt_strips,
            stats={"nets_changed": 0, "saved_mm": 0.0,
                   "krt_baseline_saved_mm": krt_stats.get("saved_mm", 0.0),
                   "gloss_errors": 1, "config": selected.as_dict(),
                   "gloss": gloss_stats.as_dict()})
