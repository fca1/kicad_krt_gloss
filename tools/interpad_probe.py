"""Find one representative G3.6 two-pad door without changing the board."""

import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "KRT" / "py_router"))
sys.path.insert(0, str(ROOT))

from kicad_dru import install_layer_clearances  # noqa: E402
from kicad_parser import parse_kicad_pcb  # noqa: E402
from list_nets import net_clearance_map_by_id, read_design_rules  # noqa: E402
from routing_config import GridRouteConfig  # noqa: E402
from dgloss.interpad import find_interpad_doors  # noqa: E402


def _config(board, pcb):
    rules = read_design_rules(str(board))
    default = (rules.get("classes", {}).get("Default", {}).get("clearance") or
               rules.get("effective", {}).get("drc_clearance") or 0.2)
    names = {net_id: net.name for net_id, net in pcb.nets.items()}
    config = GridRouteConfig(
        clearance=float(default), layers=list(pcb.board_info.copper_layers),
        net_clearances=net_clearance_map_by_id(str(board), names, rules))
    install_layer_clearances(config, None, str(board), pcb_data=pcb)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("--net")
    parser.add_argument("--max-pad-distance", type=float, default=5.0)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    parsed_at = perf_counter()
    pcb = parse_kicad_pcb(str(args.board))
    parse_ms = (perf_counter() - parsed_at) * 1000.0
    config = _config(args.board, pcb)
    net_id = None
    if args.net:
        net_id = next((nid for nid, net in pcb.nets.items()
                       if net.name == args.net), None)
        if net_id is None:
            raise SystemExit(f"unknown net: {args.net}")
    if args.repeat < 1:
        raise SystemExit("--repeat must be positive")
    scans = [find_interpad_doors(
        pcb, config, net_id=net_id,
        max_pad_distance=args.max_pad_distance) for _ in range(args.repeat)]
    scan = scans[-1]
    detection_times = [item.elapsed_ms for item in scans]
    doors = sorted(scan.doors, key=lambda door: (-abs(door.offset),
                                                  -door.admissible_width))
    reported_doors = doors if args.limit is None else doors[:max(0, args.limit)]
    result = {
        "board": str(args.board.resolve()),
        "parse_ms": round(parse_ms, 3),
        "detection_ms": round(median(detection_times), 3),
        "detection_timing": {
            "repetitions": args.repeat,
            "minimum_ms": round(min(detection_times), 3),
            "median_ms": round(median(detection_times), 3),
            "maximum_ms": round(max(detection_times), 3),
        },
        "pad_pairs": scan.pad_pairs,
        "geometric_gates": scan.geometric_gates,
        "unique_crossings": scan.unique_crossings,
        "valid_doors": len(doors),
        "reported_doors": len(reported_doors),
        "doors": [{
            "net_id": door.segment.net_id,
            "net": pcb.nets[door.segment.net_id].name,
            "layer": door.layer,
            "pads": [f"{door.pad_a.component_ref}.{door.pad_a.pad_number}",
                     f"{door.pad_b.component_ref}.{door.pad_b.pad_number}"],
            "segment": [[door.segment.start_x, door.segment.start_y],
                        [door.segment.end_x, door.segment.end_y]],
            "crossing": list(door.crossing),
            "axis": list(door.axis),
            "offset_mm": round(door.offset, 6),
            "copper_gap_mm": round(door.copper_gap, 6),
            "admissible_width_mm": round(door.admissible_width, 6),
            "current_width_mm": door.segment.width,
            "clearances_mm": [door.clearance_a, door.clearance_b],
        } for door in reported_doors],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
