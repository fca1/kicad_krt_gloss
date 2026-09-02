"""G4: deterministic multi-net passes over the complete G3.5 chain."""

from dataclasses import replace
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


def run_multinet_passes(pcb_data, config, gloss_config, net_ids, results,
                        deadline, run_g3_5):
    """Replay configured G3.5 for each net, alternating order to convergence."""
    base_order = sorted(set(net_ids))
    changes = GlossChanges()
    segment_strips = []
    via_strips = []
    changed_net_ids = set()
    passes = []
    total_changes = 0
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
        pass_changes = 0
        completed = True

        for net_id in order:
            if perf_counter() >= deadline:
                completed = False
                stop_reason = "budget"
                break
            remaining = max(0.0, deadline - perf_counter())
            one_pass = replace(
                gloss_config, budget_seconds=remaining,
                enable_multipasses=False)
            outcome = run_g3_5(
                results, pcb_data, config, one_pass, net_ids=[net_id],
                _emit_log=False)
            _collect(changes, outcome.changes)
            segment_strips.extend(outcome.input_strip_segments)
            via_strips.extend(outcome.input_strip_vias)
            stage_rows = outcome.stats.get("gloss", {}).get("stages", {})
            net_changes = sum(
                row.get("changes", 0) for stage, row in stage_rows.items()
                if stage != "G4")
            if not stage_rows:
                net_changes = (outcome.stats.get("segment_changes", 0) +
                               outcome.stats.get("via_changes", 0))

            pass_changes += net_changes
            if outcome.stats.get("nets_changed", 0):
                changed_net_ids.add(net_id)

        after = calculate_route_length(pcb_data.segments)
        elapsed_ms = (perf_counter() - pass_started) * 1000.0
        gain = max(0.0, before - after)
        passes.append({
            "index": pass_index + 1,
            "direction": "forward" if pass_index % 2 == 0 else "reverse",
            "net_ids": order,
            "changes": pass_changes,
            "saved_mm": round(gain, 4),
            "elapsed_ms": round(elapsed_ms, 3),
            "completed": completed,
        })
        print(f"Track Gloss G4 pass {pass_index + 1} "
              f"({'forward' if pass_index % 2 == 0 else 'reverse'}): "
              f"{pass_changes} transformations, -{gain:.4f} mm, "
              f"{elapsed_ms:.1f} ms")
        total_changes += pass_changes
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
        "net_ids_changed": changed_net_ids,
        "saved_mm": round(sum(row["saved_mm"] for row in passes), 4),
        "algorithm_ms": round((perf_counter() - started) * 1000.0, 3),
        "stop_reason": stop_reason,
    }
