"""Public KRT integration points for the final gloss."""

import math
from dataclasses import dataclass, field
from time import perf_counter

from check_connected import check_net_connectivity
from cleanup_pipeline import _smooth_skip_net_ids
from net_queries import calculate_route_length
from pcb_modification import smooth_octolinear_chains

from .algorithm import _connectivity_worse, shorten_routes
from .changes import GlossChanges
from .config import GlossConfig
from .context import build_gloss_context
from .pad_terminals import optimize_pad_terminals
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


def _validate_final(context, before_grades, before_length, changes):
    """One G3.5 certification over the complete post-stage board."""
    after_length = calculate_route_length(context.pcb_data.segments)
    if after_length > before_length + 1e-9:
        raise RuntimeError("G3.5 final length increased")
    for net_id, before in before_grades.items():
        if _connectivity_worse(before, _grade(context.pcb_data, net_id)):
            raise RuntimeError(f"G3.5 connectivity regression on net {net_id}")
    for entry in changes.segments:
        segment = entry.get("new")
        if segment is None:
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
                          krt_ms=0.0):
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
    gloss_stats = GlossStats(budget_seconds=selected.budget_seconds)
    started = perf_counter()
    deadline = started + max(0.0, selected.budget_seconds)

    try:
        context = build_gloss_context(
            pcb_data, config, net_ids=(net_ids or None))
        before_length = calculate_route_length(pcb_data.segments)
        before_grades = {net_id: _grade(pcb_data, net_id)
                         for net_id in context.net_ids}
        changes = GlossChanges()

        strips, added, g3_changes, g3 = shorten_routes(
            context, results, deadline=deadline)
        _append_result(results, "track_gloss_g3", added, [], g3_changes)
        changes.segments.extend(g3_changes.segments)
        changes.vias.extend(g3_changes.vias)
        gloss_stats.record("G3", changes=g3["nets_changed"],
                           saved_mm=g3["saved_mm"],
                           elapsed_ms=g3["algorithm_ms"],
                           label="nets améliorés")

        def available(enabled):
            expired = perf_counter() >= deadline
            gloss_stats.budget_expired = gloss_stats.budget_expired or expired
            return enabled and not expired, expired

        run, expired = available(selected.enable_g3_1)
        via_strips, added_vias, via_changes, via = \
            move_mobile_vias(context, results, deadline=deadline) \
            if run else ([], [], GlossChanges(), _empty_via_stats())
        _append_result(results, "track_gloss_g3_1", via["added_segments"],
                       added_vias, via_changes)
        changes.vias.extend(via_changes.vias)
        changes.segments.extend(via_changes.segments)
        gloss_stats.record("G3.1", enabled=selected.enable_g3_1,
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
        gloss_stats.record("G3.2", enabled=selected.enable_g3_2,
                           skipped_budget=expired and selected.enable_g3_2,
                           changes=pad["pads_changed"], saved_mm=pad["saved_mm"],
                           elapsed_ms=pad["algorithm_ms"], label="pads optimisés")

        run, expired = available(selected.enable_g3_3)
        node_strips, node_added, node_changes, node = \
            slide_t_nodes(context, results, deadline=deadline) \
            if run else ([], [], GlossChanges(), {
                "t_branches_slid": 0, "saved_mm": 0.0,
                "noncollinear_t_slid": 0, "right_angles_cleaned": 0,
                "net_ids_changed": set(), "algorithm_ms": 0.0})
        _append_result(results, "track_gloss_g3_3", node_added, [], node_changes)
        changes.segments.extend(node_changes.segments)
        gloss_stats.record("G3.3", enabled=selected.enable_g3_3,
                           skipped_budget=expired and selected.enable_g3_3,
                           changes=node["t_branches_slid"],
                           saved_mm=node["saved_mm"],
                           elapsed_ms=node["algorithm_ms"],
                           label="branches en T déplacées")
        if node["noncollinear_t_slid"]:
            print("Track Gloss G3.3 experimental: "
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
        gloss_stats.record("G3.4", enabled=selected.enable_g3_4,
                           skipped_budget=expired and selected.enable_g3_4,
                           changes=refine["vias_moved"],
                           saved_mm=refine["saved_mm"],
                           elapsed_ms=refine["algorithm_ms"],
                           label="vias affinés")

        after_length = _validate_final(
            context, before_grades, before_length, changes)
        changed_net_ids = {row["net_id"] for row in g3.get("per_net", [])
                           if row.get("saved_mm", 0.0) > 0.0}
        for row in (via, pad, node, refine):
            changed_net_ids.update(row["net_ids_changed"])
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
            "connectivity_regressions": 0,
        })
        print(f"Track Gloss G3.5: {len(context.net_ids)} nets parcourus, "
              f"{len(changed_net_ids)} améliorés, -{total_saved:.4f} mm, "
              f"{elapsed_ms:.1f} ms")
        if changes:
            # G3.5 owns no duplicate copper. This empty write-list entry gives
            # the plugin a User.6 aggregate of the already-certified changes.
            aggregate = {
                "segments": [dict(entry, stage="G3.5")
                             for entry in changes.segments],
                "vias": [dict(entry, stage="G3.5")
                         for entry in changes.vias],
            }
            results.append({"new_segments": [], "new_vias": [],
                            "cleanup": "track_gloss_g3_5",
                            "track_gloss_changes": aggregate})
        return GlossOutcome(
            input_strip_segments=(krt_strips + strips +
                                  via["segment_strips"] + pad_strips +
                                  node_strips + refine["segment_strips"]),
            input_strip_vias=via_strips + refine_strips,
            changes=changes.as_dict(), stats=stats)
    except Exception as exc:
        _restore(results, baseline_count, baseline_results, pcb_data,
                 baseline_segments, baseline_vias)
        print(f"Track Gloss skipped; KRT result preserved: {exc}")
        return GlossOutcome(
            input_strip_segments=krt_strips,
            stats={"nets_changed": 0, "saved_mm": 0.0,
                   "krt_baseline_saved_mm": krt_stats.get("saved_mm", 0.0),
                   "gloss_errors": 1, "config": selected.as_dict(),
                   "gloss": gloss_stats.as_dict()})
