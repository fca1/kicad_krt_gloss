"""G4: deterministic multi-net passes over the complete G3.5 chain."""

from time import perf_counter

from net_queries import calculate_route_length

from .changes import GlossChanges


def _collect(target, source):
    for entry in source.get("segments", []):
        entry["stage"] = "G4"
    for entry in source.get("vias", []):
        entry["stage"] = "G4"
    target.segments.extend(source.get("segments", []))
    target.vias.extend(source.get("vias", []))


def run_multinet_passes(context, gloss_config, net_ids, results,
                        deadline, run_g3_5):
    """Replay G3.5 once per complete pass, alternating order to convergence."""
    pcb_data = context.pcb_data
    base_order = sorted(set(net_ids).intersection(context.net_ids))
    changes = GlossChanges()
    segment_strips = []
    via_strips = []
    changed_net_ids = set()
    passes = []
    total_changes = 0
    total_segment_reduction = 0
    started = perf_counter()
    pass_index = 0
    stop_reason = "converged"

    while base_order:
        if perf_counter() >= deadline:
            stop_reason = "budget"
            break
        order = (base_order if pass_index % 2 == 0
                 else list(reversed(base_order)))
        before = calculate_route_length(pcb_data.segments)
        pass_started = perf_counter()
        outcome = run_g3_5(
            results, context, gloss_config, order, deadline, emit_log=False)
        _collect(changes, outcome["changes"].as_dict())
        segment_strips.extend(outcome["segment_strips"])
        via_strips.extend(outcome["via_strips"])
        stage_rows = outcome["stage_stats"].as_dict()["stages"]
        pass_changes = sum(
            row.get("changes", 0) for stage, row in stage_rows.items()
            if stage not in ("G4", "G5"))
        pass_segment_reduction = (
            outcome["equal"]["segments_removed"] -
            outcome["equal"]["segments_added"] +
            outcome["merged_count"])
        changed_net_ids.update(outcome["changed_net_ids"])
        completed = perf_counter() < deadline
        if not completed:
            stop_reason = "budget"

        after = calculate_route_length(pcb_data.segments)
        elapsed_ms = (perf_counter() - pass_started) * 1000.0
        gain = max(0.0, before - after)
        passes.append({
            "index": pass_index + 1,
            "direction": "forward" if pass_index % 2 == 0 else "reverse",
            "net_ids": order,
            "changes": pass_changes,
            "segment_reduction": pass_segment_reduction,
            "saved_mm": round(gain, 4),
            "elapsed_ms": round(elapsed_ms, 3),
            "completed": completed,
        })
        print(f"Track Gloss G4 pass {pass_index + 1} "
              f"({'forward' if pass_index % 2 == 0 else 'reverse'}): "
              f"{pass_changes} transformations, "
              f"-{pass_segment_reduction} segments, -{gain:.4f} mm, "
              f"{elapsed_ms:.1f} ms")
        total_changes += pass_changes
        total_segment_reduction += pass_segment_reduction
        if not completed:
            break
        if pass_changes == 0:
            stop_reason = "converged"
            break
        pass_index += 1

    return {
        "segment_strips": segment_strips,
        "via_strips": via_strips,
        "changes": changes,
        "passes": passes,
        "passes_completed": sum(row["completed"] for row in passes),
        "transformations": total_changes,
        "segment_reduction": total_segment_reduction,
        "net_ids_changed": changed_net_ids,
        "saved_mm": round(sum(row["saved_mm"] for row in passes), 4),
        "algorithm_ms": round((perf_counter() - started) * 1000.0, 3),
        "stop_reason": stop_reason,
    }
