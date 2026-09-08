"""Execute one ordered Gloss pass; candidate strategies are explicit services."""

from dataclasses import dataclass
from typing import Callable
from .execution import perf_counter
from .krt_api import calculate_route_length
from .changes import GlossChanges
from .stats import GlossStats
from .reduction_motion import MotionCertificate


@dataclass(frozen=True)
class PassOperations:
    shorten_routes: Callable
    move_mobile_vias: Callable
    optimize_pad_terminals: Callable
    slide_t_nodes: Callable
    refine_mobile_vias: Callable
    merge_collinear_in_scope: Callable
    grade: Callable
    validate_final: Callable


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


def _configure_motion(context, selected):
    """Reuse one certificate's counters across passes requiring the corridor."""
    if not selected.stay_in_corridor:
        context._reduction_motion = None
    elif getattr(context, "_reduction_motion", None) is None:
        context._reduction_motion = MotionCertificate()


def run_optimization_pass(results, context, selected, net_ids, deadline, *, operations, emit_log,
                   skip_smoothed_canonical=False):
    """Apply complementary search strategies under one optimization policy."""
    _configure_motion(context, selected)
    pcb_data = context.pcb_data
    run_net_ids = [net_id for net_id in net_ids
                   if net_id in context.net_ids]
    before_length = calculate_route_length(pcb_data.segments)
    before_grades = {net_id: operations.grade(pcb_data, net_id)
                     for net_id in run_net_ids}
    changes = GlossChanges()
    stage_stats = GlossStats(
        budget_seconds=max(0.0, deadline - perf_counter()), emit=emit_log)

    def available(enabled):
        expired = perf_counter() >= deadline
        stage_stats.budget_expired = stage_stats.budget_expired or expired
        return enabled and not expired, expired

    strips, added, g3_changes, g3 = operations.shorten_routes(
        context, results, deadline=deadline, net_ids=run_net_ids,
        include_canonical=not skip_smoothed_canonical,
        stay_in_corridor=selected.stay_in_corridor)
    _append_result(results, "track_gloss_g3", added, [], g3_changes)
    changes.segments.extend(g3_changes.segments)
    changes.vias.extend(g3_changes.vias)
    stage_stats.record("G3", changes=g3["nets_changed"],
                       saved_mm=g3["saved_mm"],
                       elapsed_ms=g3["algorithm_ms"],
                       label="nets improved")

    run, expired = available((selected.move_vias and selected.enable_g3_1))
    via_strips, added_vias, via_changes, via = \
        operations.move_mobile_vias(
            context, results, deadline=deadline, net_ids=run_net_ids) \
        if run else ([], [], GlossChanges(), _empty_via_stats())
    _append_result(results, "track_gloss_g3_1", via["added_segments"],
                   added_vias, via_changes)
    changes.vias.extend(via_changes.vias)
    changes.segments.extend(via_changes.segments)
    stage_stats.record("G3.1", enabled=(selected.move_vias and selected.enable_g3_1),
                       skipped_budget=expired and (selected.move_vias and selected.enable_g3_1),
                       changes=via["vias_moved"], saved_mm=via["saved_mm"],
                       elapsed_ms=via["algorithm_ms"], label="vias moved")

    run, expired = available(selected.optimize_pad_approaches)
    pad_strips, pad_added, pad_changes, pad = \
        operations.optimize_pad_terminals(
            context, results, deadline=deadline, net_ids=run_net_ids,
            stay_in_corridor=selected.stay_in_corridor) \
        if run else ([], [], GlossChanges(), {
            "pads_changed": 0, "saved_mm": 0.0,
            "net_ids_changed": set(), "algorithm_ms": 0.0})
    _append_result(results, "track_gloss_g3_2", pad_added, [], pad_changes)
    changes.segments.extend(pad_changes.segments)
    stage_stats.record("G3.2", enabled=selected.optimize_pad_approaches,
                       skipped_budget=expired and selected.optimize_pad_approaches,
                       changes=pad["pads_changed"], saved_mm=pad["saved_mm"],
                       elapsed_ms=pad["algorithm_ms"], label="pads optimized")

    run, expired = available(selected.move_junctions)
    node_strips, node_added, node_changes, node = \
        operations.slide_t_nodes(
            context, results, deadline=deadline,
            allow_noncollinear=selected.enable_noncollinear_t_rails,
            net_ids=run_net_ids) \
        if run else ([], [], GlossChanges(), {
            "t_branches_slid": 0, "saved_mm": 0.0,
            "noncollinear_t_slid": 0, "right_angles_cleaned": 0,
            "net_ids_changed": set(), "algorithm_ms": 0.0})
    _append_result(results, "track_gloss_g3_3", node_added, [], node_changes)
    changes.segments.extend(node_changes.segments)
    stage_stats.record("G3.3", enabled=selected.move_junctions,
                       skipped_budget=expired and selected.move_junctions,
                       changes=node["t_branches_slid"],
                       saved_mm=node["saved_mm"],
                       elapsed_ms=node["algorithm_ms"],
                       label="T branches moved")
    if emit_log and node["noncollinear_t_slid"]:
        print("Track Gloss G3.3 non-collinear variant: "
              f"{node['noncollinear_t_slid']} T junction(s) without a "
              f"collinear rail, {node['right_angles_cleaned']} "
              "90-degree bend(s) cleaned")

    run, expired = available((selected.move_vias and selected.enable_g3_4))
    refine_strips, refine_vias, refine_changes, refine = \
        operations.refine_mobile_vias(
            context, results, deadline=deadline, net_ids=run_net_ids) \
        if run else ([], [], GlossChanges(), _empty_via_stats())
    _append_result(results, "track_gloss_g3_4", refine["added_segments"],
                   refine_vias, refine_changes)
    changes.vias.extend(refine_changes.vias)
    changes.segments.extend(refine_changes.segments)
    stage_stats.record("G3.4", enabled=(selected.move_vias and selected.enable_g3_4),
                       skipped_budget=expired and (selected.move_vias and selected.enable_g3_4),
                       changes=refine["vias_moved"],
                       saved_mm=refine["saved_mm"],
                       elapsed_ms=refine["algorithm_ms"],
                       label="vias refined")

    run, expired = available(True)
    equal_strips, equal_added, equal_changes, equal = \
        operations.shorten_routes(
            context, results, deadline=deadline,
            objective="fewer_segments", stage="G3.5",
            net_ids=run_net_ids, stay_in_corridor=selected.stay_in_corridor) \
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
        label="segments removed at equal length")

    run, expired = available(True)
    merge_before = list(pcb_data.segments)
    merge_started = perf_counter()
    if run:
        merged_count, merged_nets, merge_strips, merge_added, merge = \
            operations.merge_collinear_in_scope(results, context, run_net_ids)
    else:
        merged_count, merged_nets = 0, 0
        merge_strips, merge_added = [], []
        merge = {"joints": 0, "segs_removed": 0, "segs_added": 0,
                 "nets_skipped_large": 0}
    merge_ms = (perf_counter() - merge_started) * 1000.0
    final_segment_ids = {id(segment) for segment in pcb_data.segments}
    merge_removed = [segment for segment in merge_before
                     if id(segment) not in final_segment_ids]
    if merge_removed and not context.branch_scoped:
        context.replace_editable_segments(merge_removed, merge_added)
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
        elapsed_ms=merge_ms, label="collinear joints removed")

    if not selected.stay_in_corridor:
        local_strips, local_added, local_changes, local_stats = operations.shorten_routes(
            context, results, deadline=deadline, net_ids=run_net_ids,
            local_only=True, stage="G3 local")
        _append_result(results, "track_gloss_local", local_added, [], local_changes)
        strips.extend(local_strips)
        changes.segments.extend(local_changes.segments)
        stage_stats.record("G3 local", changes=local_stats["nets_changed"],
                           saved_mm=local_stats["saved_mm"],
                           elapsed_ms=local_stats["algorithm_ms"], label="local reductions")

    after_length = operations.validate_final(
        context, before_grades, before_length, changes)
    changed_net_ids = {row["net_id"] for row in g3.get("per_net", [])
                       if row.get("saved_mm", 0.0) > 0.0}
    for row in (via, pad, node, refine):
        changed_net_ids.update(row["net_ids_changed"])
    changed_net_ids.update(
        entry["old"].net_id for entry in equal_changes.segments
        if "old" in entry)
    changed_net_ids.update(segment.net_id for segment in merge_removed)
    if not selected.stay_in_corridor:
        changed_net_ids.update(entry["old"].net_id for entry in local_changes.segments
                               if "old" in entry)

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
