"""Test-only KRT/dgloss comparison helpers; no CLI and no production hook."""

from copy import deepcopy
from time import perf_counter

from check_connected import check_net_connectivity
from net_queries import net_copper_length
from pcb_modification import smooth_octolinear_chains

from .algorithm import shorten_routes
from .context import build_gloss_context


def _grade(pcb_data, net_id):
    return check_net_connectivity(
        net_id,
        [s for s in pcb_data.segments if s.net_id == net_id],
        [v for v in pcb_data.vias if v.net_id == net_id],
        pcb_data.pads_by_net.get(net_id, []), [], pcb_data=pcb_data)


def _not_worse(before, after):
    return not ((before.get("connected") and not after.get("connected")) or
                len(after.get("disconnected_pads") or []) >
                len(before.get("disconnected_pads") or []) or
                (after.get("num_components") or 1) >
                (before.get("num_components") or 1))


def compare_smoothers(pcb_data, config, net_ids=None):
    """Compare KRT and G3 independently, net by net, from identical copper."""
    selected = sorted(net_ids or {s.net_id for s in pcb_data.segments if s.net_id})
    rows = []
    for net_id in selected:
        initial_segments = sum(s.net_id == net_id for s in pcb_data.segments)
        initial_length = net_copper_length(pcb_data, net_id)
        initial_grade = _grade(pcb_data, net_id)

        krt_board = deepcopy(pcb_data)
        krt_results = []
        started = perf_counter()
        smooth_octolinear_chains(
            krt_results, krt_board, {net_id},
            clearance=config.clearance,
            net_clearances=getattr(config, "net_clearances", None),
            board_edge_clearance=config.board_edge_clearance,
            config=config, min_gain=config.grid_step)
        krt_ms = (perf_counter() - started) * 1000.0
        krt_length = net_copper_length(krt_board, net_id)

        gloss_board = deepcopy(pcb_data)
        gloss_results = []
        started = perf_counter()
        context = build_gloss_context(gloss_board, config, net_ids=[net_id])
        preparation_ms = (perf_counter() - started) * 1000.0
        started = perf_counter()
        _strips, _added, _changes, stats = shorten_routes(
            context, gloss_results, net_ids=context.net_ids)
        gloss_ms = (perf_counter() - started) * 1000.0
        gloss_length = net_copper_length(gloss_board, net_id)

        rows.append({
            "net_id": net_id,
            "net_name": getattr(pcb_data.nets.get(net_id), "name", str(net_id)),
            "initial_mm": initial_length,
            "initial_segments": initial_segments,
            "krt_final_mm": krt_length,
            "krt_saved_mm": initial_length - krt_length,
            "krt_segments": sum(s.net_id == net_id for s in krt_board.segments),
            "krt_valid": _not_worse(initial_grade, _grade(krt_board, net_id)),
            "krt_ms": krt_ms,
            "dgloss_final_mm": gloss_length,
            "dgloss_saved_mm": initial_length - gloss_length,
            "dgloss_segments": sum(s.net_id == net_id for s in gloss_board.segments),
            "dgloss_valid": _not_worse(initial_grade, _grade(gloss_board, net_id)),
            "dgloss_preparation_ms": preparation_ms,
            "dgloss_ms": gloss_ms,
            "dgloss_total_ms": preparation_ms + gloss_ms,
            "vias_moved": 0,
            "dgloss_stats": stats,
        })
    return rows


def format_comparison_table(rows):
    """Render the compact Markdown table used by the dispenser test report."""
    lines = [
        "| Net | Initiale | KRT gain / segments / temps | "
        "dgloss gain / segments / préparation + algo | Valide |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['net_name']} | {row['initial_mm']:.3f} mm / "
            f"{row['initial_segments']} | {row['krt_saved_mm']:.3f} mm / "
            f"{row['krt_segments']} / {row['krt_ms']:.1f} ms | "
            f"{row['dgloss_saved_mm']:.3f} mm / {row['dgloss_segments']} / "
            f"{row['dgloss_preparation_ms']:.1f} + {row['dgloss_ms']:.1f} ms | "
            f"KRT {'oui' if row['krt_valid'] else 'non'}, "
            f"dgloss {'oui' if row['dgloss_valid'] else 'non'} |")
    return "\n".join(lines)
