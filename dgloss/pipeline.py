"""Public KRT integration points for the final gloss."""

from .execution import perf_counter
from .topology import terminal_partition as _terminal_partition
from dgloss.krt_api import calculate_route_length
from dgloss.krt_api import merge_collinear_segments
from .algorithm import shorten_routes
from .branches import elementary_branch_segment_ids
from .changes import GlossChanges, release_result_custody
from .config import GlossConfig
from .context import build_gloss_context, resolve_gloss_scope
from .pad_terminals import optimize_pad_terminals
from .passes import run_multinet_passes
from .sliding_nodes import slide_t_nodes
from .stats import GlossStats
from .via_mobile import move_mobile_vias, refine_mobile_vias
from .transaction import (GlossOutcome, _result_snapshot, _restore)
from .outcome_geometry import (_route_signature, _final_visual_changes)
from .certification import _g5_grade
from . import certification
from .optimization import PassOperations, run_optimization_pass, _append_result


def _grade(pcb_data, net_id):
    # Local and pass-level validation must use the same electrical model.
    from .board_views import board_views
    from .topology import reference_connectivity
    views = board_views(pcb_data)
    return reference_connectivity(pcb_data, net_id, views.segments(net_id),
                                  views.vias(net_id))


def _merge_collinear_in_scope(results, context, net_ids):
    """KRT proposes; exact support and electrical checks authorize publication."""
    from .krt_merge import merge_in_scope
    return merge_in_scope(results, context, net_ids, merge_collinear_segments)


def run_final_gloss(results, pcb_data, config, gloss_config=None, *,
                    net_ids=None, excluded_net_ids=None, seed_segments=None):
    """Shared transactional entry point for plugin and command-line callers."""
    return run_post_smooth_gloss(
        results, pcb_data, config, gloss_config, net_ids=net_ids,
        excluded_net_ids=excluded_net_ids, seed_segments=seed_segments)


def run_post_smooth_gloss(results, pcb_data, config, gloss_config=None, *,
                          net_ids=None, krt_strips=None, krt_stats=None,
                          krt_ms=0.0, excluded_net_ids=None, _emit_log=True,
                          _resolved_scope=None,
                          krt_smooth_complete=False, seed_segments=None,
                          _editable_segment_ids=None, _branch_count=0,
                          _input_before_length=None, _input_signatures=None,
                          _visual_baseline_segments=None,
                          _visual_baseline_vias=None, _total_started=None):
    """Transactional optimization engine (legacy entry-point name).

    krt_smooth_complete is accepted for compatibility, but never disables a
    candidate family: every caller gets the same search and safety policy.
    """
    baseline_segments = list(pcb_data.segments)
    baseline_vias = list(pcb_data.vias)
    visual_baseline_segments = (
        baseline_segments if _visual_baseline_segments is None else
        list(_visual_baseline_segments))
    visual_baseline_vias = (
        baseline_vias if _visual_baseline_vias is None else
        list(_visual_baseline_vias))
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
        if seed_segments:
            seeded_net_ids = {segment.net_id for segment in seed_segments
                              if segment.net_id}
            net_ids = (seeded_net_ids if not net_ids else
                       set(net_ids).intersection(seeded_net_ids))
            if not net_ids:
                raise RuntimeError(
                    "selected seeds do not belong to the requested nets")
        if _resolved_scope is None:
            scope_net_ids, excluded, exclusion_reasons = resolve_gloss_scope(
                pcb_data, net_ids, excluded_net_ids)
        else:
            scope_net_ids, excluded, exclusion_reasons = _resolved_scope
        if seed_segments and _editable_segment_ids is None:
            _editable_segment_ids, _branch_count = \
                elementary_branch_segment_ids(pcb_data, seed_segments)
            if not _editable_segment_ids:
                raise RuntimeError(
                    "no elementary branch matched the selected seed")
        context = build_gloss_context(
            pcb_data, config, net_ids=scope_net_ids,
            excluded_net_ids=excluded, exclusion_reasons=exclusion_reasons,
            editable_segment_ids=_editable_segment_ids)
        if _emit_log and _editable_segment_ids is not None:
            print(f"Track Gloss G0: {_branch_count} elementary branch(es), "
                  f"{len(_editable_segment_ids)} editable segment(s)")
        if _emit_log and excluded:
            print(f"Track Gloss G0: {len(excluded)} protected net(s) excluded")
        board_before_length = calculate_route_length(pcb_data.segments)
        before_length = calculate_route_length([
            segment for segment in pcb_data.segments
            if segment.net_id in scope_net_ids])
        before_grades = {net_id: _grade(pcb_data, net_id)
                         for net_id in scope_net_ids}
        g5_before_grades = before_grades
        initial = _run_optimization_pass(
            results, context, selected, scope_net_ids, deadline,
            emit_log=_emit_log,
            skip_smoothed_canonical=False)
        changes = initial["changes"]
        gloss_stats = initial["stage_stats"]
        g3, via, pad = dict(initial["g3"]), dict(initial["via"]), dict(initial["pad"])
        node, refine = dict(initial["node"]), dict(initial["refine"])
        equal = dict(initial["equal"])
        merged_count, merged_nets = (initial["merged_count"],
                                     initial["merged_nets"])
        merge, merge_ms = dict(initial["merge"]), initial["merge_ms"]

        gloss_stats.budget_expired |= perf_counter() >= deadline
        run = selected.repeat_until_stable
        g4_started = perf_counter()
        g4 = run_multinet_passes(
            context, selected, list(context.net_ids), results,
            deadline, _run_optimization_pass,
            initial_gain=max(0.0, initial["before_length"] -
                             initial["after_length"])) if run else {
                "segment_strips": [], "via_strips": [],
                "changes": GlossChanges(), "passes": [],
                "passes_completed": 0, "transformations": 0,
                "segment_reduction": 0,
                "net_ids_changed": set(), "saved_mm": 0.0,
                "algorithm_ms": 0.0,
                "stop_reason": "disabled",
            }
        # G4 consumes passes, not the time available to the other stages.
        deadline += perf_counter() - g4_started
        # Public operation counters cover every pass, not only the first one.
        for name, counters in (("g3", g3), ("via", via), ("pad", pad),
                               ("node", node), ("refine", refine),
                               ("equal", equal), ("merge", merge)):
            for key, value in g4.get("operation_totals", {}).get(name, {}).items():
                counters[key] = counters.get(key, 0) + value
        merge_totals = g4.get("operation_totals", {}).get("merge_summary", {})
        merged_count += merge_totals.get("merged_count", 0)
        merged_nets += merge_totals.get("merged_nets", 0)
        merge_ms += merge_totals.get("merge_ms", 0)
        changes.segments.extend(g4["changes"].segments)
        changes.vias.extend(g4["changes"].vias)
        gloss_stats.record(
            "G4", enabled=selected.repeat_until_stable,
            skipped_budget=False,
            changes=g4["transformations"], saved_mm=g4["saved_mm"],
            elapsed_ms=g4["algorithm_ms"], label="multi-net transformations")

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
            label="final objects certified")
        changed_net_ids = set(initial["changed_net_ids"])
        changed_net_ids.update(g4["net_ids_changed"])
        if _input_signatures is not None:
            changed_net_ids = {
                net_id for net_id in scope_net_ids
                if _input_signatures.get(net_id) !=
                _route_signature(pcb_data, net_id)}
        elapsed_ms = (perf_counter() - (
            started if _total_started is None else _total_started)) * 1000.0
        input_before_length = (before_length if _input_before_length is None
                               else float(_input_before_length))
        krt_saved = input_before_length - before_length
        post_krt_saved = before_length - after_length
        total_saved = round(input_before_length - after_length, 4)
        stats = dict(g3)
        stats.update({
            "config": selected.as_dict(), "gloss": gloss_stats.as_dict(),
            "nets_processed": len(context.net_ids),
            "nets_excluded": len(context.excluded_net_ids),
            "excluded_net_ids": sorted(context.excluded_net_ids),
            "exclusion_reasons": dict(context.exclusion_reasons),
            "nets_changed": len(changed_net_ids), "saved_mm": total_saved,
            "elementary_branches": int(_branch_count),
            "branch_scoped": _editable_segment_ids is not None,
            "editable_layers": list(config.layers),
            "segment_changes": len(changes.segments),
            "via_changes": len(changes.vias),
            "before_mm": round(input_before_length, 4),
            "krt_after_mm": round(before_length, 4),
            "after_mm": round(after_length, 4),
            "total_ms": round(elapsed_ms, 3),
            "krt_baseline_ms": round(krt_ms, 3),
            "krt_baseline_saved_mm": round(krt_saved, 4),
            "post_krt_saved_mm": round(post_krt_saved, 4),
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
            "merge_rejected_nets": merge.get("rejected_nets", 0),
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
        stats["pad_distance_cache"] = context.clearance_adapter._pad_distance.cache_info()._asdict()
        stats["copper_data_cache"] = dict(context.clearance_adapter.copper_data_stats)
        stats["search_cache"] = dict(context.search_cache.stats)
        stats["zone_invalidations"] = context.zone_invalidations
        motion = getattr(context, "_reduction_motion", None)
        stats["corridor_motion"] = dict(motion.stats) if motion is not None else {}
        if _emit_log:
            copper_delta = (f"-{total_saved:.4f}" if total_saved >= 0.0 else
                            f"+{-total_saved:.4f}")
            print(f"Track Gloss final: {len(context.net_ids)} nets processed, "
                  f"{len(changed_net_ids)} changed, {copper_delta} mm, "
                  f"{elapsed_ms:.1f} ms")
        # Visualisation is always one final delta on the first free
        # User layer (or the layer already owned by Track Gloss).
        # The multipass switch controls optimisation only; it must never bring
        # back the historical G3--G3.5 overlays on User.2 through User.6.
        final_visual = _final_visual_changes(
            visual_baseline_segments, visual_baseline_vias, pcb_data, changes)
        for result in results[baseline_count:]:
            result.pop("track_gloss_changes", None)
        if final_visual:
            results.append({
                "new_segments": [], "new_vias": [],
                "cleanup": "track_gloss_final_visualization",
                "track_gloss_changes": final_visual.as_dict(),
            })
        return GlossOutcome(
            input_strip_segments=(krt_strips +
                                  initial["segment_strips"] +
                                  g4["segment_strips"]),
            input_strip_vias=(initial["via_strips"] +
                              g4["via_strips"]),
            changes=changes.as_dict(), visual_changes=final_visual.as_dict(),
            stats=stats)
    except Exception as exc:
        _restore(results, baseline_count, baseline_results, pcb_data,
                 baseline_segments, baseline_vias)
        if _emit_log:
            print(f"Track Gloss skipped; input preserved: {exc}")
        return GlossOutcome(
            input_strip_segments=krt_strips,
            stats={"nets_changed": 0, "saved_mm": 0.0,
                   "krt_baseline_saved_mm": krt_stats.get("saved_mm", 0.0),
                   "gloss_errors": 1, "config": selected.as_dict(),
                   "gloss": gloss_stats.as_dict()})


def _validate_final(context, before_grades, before_length, changes):
    return certification._validate_final(context, before_grades, before_length,
                                       changes, grade=_grade)

def _certify_g5_copper(context, before_grades, changes):
    return certification._certify_g5_copper(context, before_grades, changes,
                                          grade=_g5_grade)


def _run_optimization_pass(results, context, selected, net_ids, deadline, *,
                           emit_log, skip_smoothed_canonical=False):
    operations = PassOperations(shorten_routes, move_mobile_vias,
        optimize_pad_terminals, slide_t_nodes, refine_mobile_vias,
        _merge_collinear_in_scope, _grade, _validate_final)
    return run_optimization_pass(results, context, selected, net_ids, deadline,
        operations=operations, emit_log=emit_log,
        skip_smoothed_canonical=skip_smoothed_canonical)
