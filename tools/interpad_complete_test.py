"""Run the first complete M01 centering test without changing the board."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "KRT" / "py_router"))
sys.path.insert(0, str(ROOT))

from check_connected import check_net_connectivity  # noqa: E402
from dgloss.interpad import (center_with_sliding_neighbors,
                             find_interpad_doors)  # noqa: E402
from dgloss.krt_clearance import KrtClearanceAdapter  # noqa: E402
from kicad_parser import parse_kicad_pcb  # noqa: E402
from tools.interpad_probe import _config  # noqa: E402


def _segment_json(segment):
    return {
        "start": [segment.start_x, segment.start_y],
        "end": [segment.end_x, segment.end_y],
        "width_mm": segment.width,
        "layer": segment.layer,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("--net", required=True)
    args = parser.parse_args()

    pcb = parse_kicad_pcb(str(args.board))
    config = _config(args.board, pcb)
    net_id = next((nid for nid, net in pcb.nets.items()
                   if net.name == args.net), None)
    if net_id is None:
        raise SystemExit(f"unknown net: {args.net}")

    started = perf_counter()
    scan = find_interpad_doors(pcb, config, net_id=net_id)
    door = max(scan.doors, key=lambda item: abs(item.offset), default=None)
    candidate = center_with_sliding_neighbors(pcb, door) if door else None
    construction_ms = (perf_counter() - started) * 1000.0
    if candidate is None:
        raise SystemExit("no complete sliding candidate")

    source_ids = {id(segment) for segment in candidate.source_segments}
    current = [segment for segment in pcb.segments if segment.net_id == net_id]
    trial = [segment for segment in current if id(segment) not in source_ids] + \
            list(candidate.segments)
    vias = [via for via in pcb.vias if via.net_id == net_id]
    pads = pcb.pads_by_net.get(net_id, [])

    checked = perf_counter()
    clearance_ok = KrtClearanceAdapter(pcb, config).connector_clears(
        candidate.segments)
    before_grade = check_net_connectivity(
        net_id, current, vias, pads, [], pcb_data=pcb)
    after_grade = check_net_connectivity(
        net_id, trial, vias, pads, [], pcb_data=pcb)
    validation_ms = (perf_counter() - checked) * 1000.0
    connectivity_ok = (
        not before_grade.get("connected") or after_grade.get("connected")) and \
        len(after_grade.get("disconnected_pads") or []) <= \
        len(before_grade.get("disconnected_pads") or []) and \
        (after_grade.get("num_components") or 1) <= \
        (before_grade.get("num_components") or 1)

    def grade_summary(grade):
        return {
            "connected": bool(grade.get("connected")),
            "num_components": grade.get("num_components"),
            "disconnected_pad_count": len(grade.get("disconnected_pads") or []),
        }

    result = {
        "board": str(args.board.resolve()),
        "net": args.net,
        "door": [f"{door.pad_a.component_ref}.{door.pad_a.pad_number}",
                 f"{door.pad_b.component_ref}.{door.pad_b.pad_number}"],
        "axis": list(door.axis),
        "original_crossing": list(door.crossing),
        "translation": list(candidate.translation),
        "source_segments": [_segment_json(segment)
                            for segment in candidate.source_segments],
        "candidate_segments": [_segment_json(segment)
                               for segment in candidate.segments],
        "source_segment_count": len(candidate.source_segments),
        "candidate_segment_count": len(candidate.segments),
        "before_length_mm": round(candidate.before_length, 6),
        "after_length_mm": round(candidate.after_length, 6),
        "length_delta_mm": round(candidate.after_length -
                                 candidate.before_length, 6),
        "clearance_ok": clearance_ok,
        "connectivity_ok": connectivity_ok,
        "before_connectivity": grade_summary(before_grade),
        "after_connectivity": grade_summary(after_grade),
        "detection_and_construction_ms": round(construction_ms, 3),
        "validation_ms": round(validation_ms, 3),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if not clearance_ok or not connectivity_ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
