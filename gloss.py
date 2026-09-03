#!/usr/bin/env python3
"""Apply Track Gloss to a routed KiCad board using KRT's CLI contracts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from time import perf_counter

from kicad_krt_gloss.runtime import configure_krt_runtime


configure_krt_runtime()

import routing_defaults as defaults
from copy_board import copy_board
from dgloss import GlossConfig, run_post_smooth_gloss
from kicad_dru import install_layer_clearances, install_track_clearances
from kicad_parser import parse_kicad_pcb
from list_nets import (board_default_netclass_clearance,
                       board_default_netclass_param,
                       net_clearance_map_by_id, resolve_cli_floor)
from net_queries import (expand_net_patterns, nets_for_components,
                         suggest_component_refs)
from output_writer import write_routed_output
from routing_common import resolve_net_ids
from routing_config import GridRouteConfig
from routing_constants import POWER_NET_EXCLUSION_PATTERNS


def build_parser():
    parser = argparse.ArgumentParser(
        description="Apply the final Track Gloss to an already routed KiCad PCB.")
    parser.add_argument("input_file", help="Input KiCad PCB file")
    parser.add_argument("output_file", nargs="?",
                        help="Output PCB (default: input_gloss.kicad_pcb)")
    parser.add_argument("net_patterns", nargs="*",
                        help="Net names or wildcard patterns (default: '*')")
    parser.add_argument("--output", metavar="FILE",
                        help="Named alias for positional output_file")
    parser.add_argument("--overwrite", "-O", action="store_true")
    parser.add_argument("--nets", "-n", nargs="+",
                        help="Net names or wildcard patterns")
    parser.add_argument("--component", "-C", nargs="+", metavar="REF",
                        help="Gloss all nets connected to these components")
    parser.add_argument("--group", metavar="BLOCK",
                        help="Gloss the nets of one KRT placement block")
    parser.add_argument("--group-by", default="auto", metavar="SOURCES",
                        help="KRT placement-group sources (default: auto)")
    parser.add_argument("--group-scope", choices=("touching", "internal"),
                        default="touching")
    parser.add_argument("--list-groups", action="store_true")
    parser.add_argument("--preview", action="store_true",
                        help="Run and report without writing a PCB")
    parser.add_argument("--json-out", metavar="FILE",
                        help="Write the full JSON_SUMMARY to FILE")
    parser.add_argument(
        "--debug-layer", choices=("auto",) + tuple(
            f"User.{index}" for index in range(1, 10)),
        help=("Write the final before/after overlay: 'auto' selects the first "
              "free User layer, or specify User.1 through User.9"))

    parser.add_argument("--layers", "-l", nargs="+", default=None)
    parser.add_argument("--grid-step", type=float, default=defaults.GRID_STEP)
    parser.add_argument("--track-width", type=float, default=None)
    parser.add_argument("--clearance", type=float, default=None)
    parser.add_argument("--via-size", type=float, default=None)
    parser.add_argument("--via-drill", type=float, default=None)
    parser.add_argument("--net-clearances", metavar="JSON", default=None)
    parser.add_argument("--board-edge-clearance", type=float, default=None)
    parser.add_argument("--hole-to-hole-clearance", type=float, default=None)

    parser.add_argument("--budget-seconds", type=float, default=20.0)
    parser.add_argument("--no-g3-1", action="store_true")
    parser.add_argument("--no-g3-2", action="store_true")
    parser.add_argument("--no-g3-3", action="store_true")
    parser.add_argument("--no-g3-4", action="store_true")
    parser.add_argument("--no-noncollinear-t-rails", action="store_true")
    parser.add_argument("--no-multipasses", action="store_true")
    return parser


def list_groups(pcb_data, sources):
    import _placer_path  # noqa: F401
    from group_routing import block_net_names
    from placement.groups import derive_groups, parse_sources, short_name

    groups = derive_groups(pcb_data, parse_sources(sources))
    print(f"{len(groups)} placement block(s) from {sources!r}:")
    for name, refs in sorted(groups.items(),
                             key=lambda item: (-len(item[1]), item[0])):
        touching = len(block_net_names(pcb_data, refs, "touching"))
        internal = len(block_net_names(pcb_data, refs, "internal"))
        print(f"  {short_name(name):34s} parts={len(refs):3d}  nets: "
              f"touching={touching:3d} internal={internal:3d}")


def resolve_scope(parser, args, pcb_data):
    patterns = list(args.net_patterns or []) + list(args.nets or [])
    patterns = [pattern.strip() for pattern in patterns if pattern.strip()]
    components = [ref.strip() for ref in (args.component or []) if ref.strip()]
    explicit_patterns = bool(patterns)
    if not patterns and not components and not args.group:
        patterns = ["*"]

    names = expand_net_patterns(pcb_data, patterns) if patterns else []
    if components:
        selection = nets_for_components(
            pcb_data, components,
            exclude_patterns=None if explicit_patterns
            else POWER_NET_EXCLUSION_PATTERNS)
        if selection.unmatched_patterns:
            refs = sorted(set(pcb_data.footprints or {}))
            detail = "; ".join(
                f"{ref!r}{suggest_component_refs(refs, ref)}"
                for ref in selection.unmatched_patterns)
            parser.error(f"--component matched no footprint: {detail}")
        component_nets = set(selection.net_names)
        names = ([name for name in names if name in component_nets]
                 if patterns else list(selection.net_names))
        print(f"Matched {len(selection.matched_refs)} footprint(s) -> "
              f"{len(names)} nets")
        if selection.excluded_names:
            print(f"  dropped {len(selection.excluded_names)} power/ground net(s): "
                  f"{', '.join(selection.excluded_names[:5])}")

    if args.group:
        if not args.group.strip():
            parser.error("--group was given an empty name")
        import _placer_path  # noqa: F401
        from group_routing import (GroupRoutingError, block_net_names,
                                   block_refs, describe_scope, resolved_name)
        from placement.groups import GroupError, parse_sources
        try:
            sources = parse_sources(args.group_by)
            refs = block_refs(pcb_data, args.group, sources)
        except (GroupError, GroupRoutingError) as exc:
            parser.error(str(exc))
        resolved = resolved_name(pcb_data, args.group, sources)
        if resolved and resolved != args.group:
            print(f"  --group {args.group!r} resolved to block {resolved!r}")
        group_nets = set(block_net_names(pcb_data, refs, args.group_scope))
        names = ([name for name in names if name in group_nets]
                 if patterns or components else sorted(group_nets))
        print(describe_scope(pcb_data, refs, args.group_scope,
                             final=len(names) if patterns or components else None))

    if not names:
        parser.error("no nets matched the requested scope")
    resolved = resolve_net_ids(pcb_data, names)
    if not resolved:
        parser.error("none of the requested net names exist on this board")
    return resolved


def _board_value(path, key, fallback, explicit):
    if explicit is not None:
        return explicit
    value = board_default_netclass_param(path, key)
    return value if value is not None else fallback


def build_krt_config(args, pcb_data, net_ids):
    default_clearance = board_default_netclass_clearance(args.input_file)
    if args.clearance is None:
        clearance = (default_clearance if default_clearance is not None
                     else defaults.CLEARANCE)
    else:
        clearance = (min(default_clearance, args.clearance)
                     if default_clearance is not None else args.clearance)
    layers = (list(args.layers) if args.layers else
              list(pcb_data.board_info.copper_layers or defaults.DEFAULT_LAYERS))
    edge = resolve_cli_floor(
        args.input_file, "board_edge_clearance", args.board_edge_clearance,
        defaults.BOARD_EDGE_CLEARANCE, "--board-edge-clearance")
    hole = resolve_cli_floor(
        args.input_file, "hole_to_hole", args.hole_to_hole_clearance,
        defaults.HOLE_TO_HOLE_CLEARANCE, "--hole-to-hole-clearance")
    config = GridRouteConfig(
        track_width=_board_value(args.input_file, "track_width",
                                 defaults.TRACK_WIDTH, args.track_width),
        clearance=clearance,
        via_size=_board_value(args.input_file, "via_diameter",
                              defaults.VIA_SIZE, args.via_size),
        via_drill=_board_value(args.input_file, "via_drill",
                               defaults.VIA_DRILL, args.via_drill),
        grid_step=args.grid_step, layers=layers,
        board_edge_clearance=edge, hole_to_hole_clearance=hole)

    if args.net_clearances:
        with open(args.net_clearances, encoding="utf-8") as handle:
            by_name = json.load(handle)
        config.net_clearances = {
            net_id: float(by_name[net.name])
            for net_id, net in pcb_data.nets.items() if net.name in by_name}
    else:
        config.net_clearances = net_clearance_map_by_id(
            args.input_file,
            {net_id: net.name for net_id, net in pcb_data.nets.items()})
        if args.clearance is not None:
            config.net_clearances = {
                net_id: min(value, args.clearance)
                for net_id, value in config.net_clearances.items()}
    config.set_net_clearances(config.net_clearances, net_ids)
    install_layer_clearances(config, None, args.input_file, pcb_data)
    install_track_clearances(
        config, None, args.input_file, pcb_data, routed_net_ids=net_ids)
    return config


def make_summary(args, names, outcome, wall_ms, debug_layer=None):
    stats = outcome.stats
    before = float(stats.get("before_mm", 0.0))
    saved = float(stats.get("saved_mm", 0.0))
    if saved == 0.0:
        saved = 0.0
    return {
        "tool": "dgloss", "scope": "run",
        "input": os.path.abspath(args.input_file),
        "output": None if args.preview else os.path.abspath(args.output_file),
        "preview": bool(args.preview), "selected_nets": len(names),
        "debug_layer": debug_layer,
        "net_names": names,
        "nets_processed": int(stats.get("nets_processed", 0)),
        "nets_excluded": int(stats.get("nets_excluded", 0)),
        "excluded_net_ids": list(stats.get("excluded_net_ids", [])),
        "exclusion_reasons": dict(stats.get("exclusion_reasons", {})),
        "nets_changed": int(stats.get("nets_changed", 0)),
        "before_mm": before, "after_mm": float(stats.get("after_mm", before)),
        "saved_mm": saved,
        "saved_percent": round(100.0 * saved / before, 4) if before else 0.0,
        "segment_changes": int(stats.get("segment_changes", 0)),
        "via_changes": int(stats.get("via_changes", 0)),
        "g4_passes_completed": int(stats.get("g4_passes_completed", 0)),
        "g4_stop_reason": stats.get("g4_stop_reason"),
        "g5_valid": bool(stats.get("g5_valid", False)),
        "budget_expired": bool(stats.get("gloss", {}).get("budget_expired", False)),
        "stages": stats.get("gloss", {}).get("stages", {}),
        "algorithm_ms": float(stats.get("total_ms", 0.0)),
        "wall_ms": round(wall_ms, 3),
        "complete": not bool(stats.get("gloss_errors", 0)),
        "statistics": stats,
    }


def write_output(args, pcb_data, results, outcome):
    wrote = write_routed_output(
        args.input_file, args.output_file, results, [], [], [], [], [], pcb_data,
        segments_to_remove=outcome.input_strip_segments,
        vias_to_remove=outcome.input_strip_vias)
    if not wrote and os.path.abspath(args.input_file) != os.path.abspath(args.output_file):
        copy_board(args.input_file, args.output_file)


def main(argv=None):
    try:
        from redo_record import record_invocation
        record_invocation()
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not os.path.isfile(args.input_file):
        parser.error(f"input file not found: {args.input_file}")
    if args.output and args.output_file and args.output != args.output_file:
        parser.error("specify output once: positional output_file OR --output")
    args.output_file = args.output or args.output_file
    if args.output_file is None:
        base, ext = os.path.splitext(args.input_file)
        args.output_file = args.input_file if args.overwrite else base + "_gloss" + ext

    pcb_data = parse_kicad_pcb(args.input_file)
    if args.list_groups:
        try:
            list_groups(pcb_data, args.group_by)
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    resolved = resolve_scope(parser, args, pcb_data)
    names = [name for name, _net_id in resolved]
    net_ids = [net_id for _name, net_id in resolved]
    print(f"Glossing {len(names)} nets: {names[:5]}{'...' if len(names) > 5 else ''}")

    config = build_krt_config(args, pcb_data, net_ids)
    gloss_config = GlossConfig(
        enable_g3_1=not args.no_g3_1, enable_g3_2=not args.no_g3_2,
        enable_g3_3=not args.no_g3_3, enable_g3_4=not args.no_g3_4,
        budget_seconds=max(0.0, args.budget_seconds),
        enable_noncollinear_t_rails=not args.no_noncollinear_t_rails,
        enable_multipasses=not args.no_multipasses)
    results = []
    started = perf_counter()
    outcome = run_post_smooth_gloss(
        results, pcb_data, config, gloss_config, net_ids=net_ids)
    wall_ms = (perf_counter() - started) * 1000.0
    debug_layer = None
    if not args.preview:
        write_output(args, pcb_data, results, outcome)
        if args.debug_layer:
            from kicad_krt_gloss.debug_overlay import write_cli_debug_overlay
            try:
                debug_layer = write_cli_debug_overlay(
                    args.output_file, outcome.visual_changes, args.debug_layer)
            except Exception as exc:
                print(f"Track Gloss: {exc}; debug overlay skipped")

    summary = make_summary(args, names, outcome, wall_ms, debug_layer)
    print("\n=== TRACK GLOSS SUMMARY ===")
    print(f"Nets: {summary['nets_processed']} processed, "
          f"{summary['nets_changed']} improved")
    gain = (f"-{summary['saved_mm']:.4f}"
            if summary["saved_mm"] > 0.0 else "0.0000")
    print(f"Length: {summary['before_mm']:.4f} -> {summary['after_mm']:.4f} mm "
          f"({gain} mm, {summary['saved_percent']:.4f}%)")
    print(f"Changes: {summary['segment_changes']} segment, "
          f"{summary['via_changes']} via; G4 passes: "
          f"{summary['g4_passes_completed']}; {summary['wall_ms']:.1f} ms")
    if debug_layer:
        print(f"Debug overlay: {debug_layer} (\"TrackGloss Changes\")")
    print("JSON_SUMMARY: " + json.dumps(summary, sort_keys=True))
    compact = {key: summary[key] for key in
               ("complete", "selected_nets", "nets_changed", "saved_mm",
                "segment_changes", "via_changes", "g4_passes_completed",
                "g5_valid", "wall_ms")}
    print("JSON_SUMMARY_MIN: " + json.dumps(compact, sort_keys=True))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
