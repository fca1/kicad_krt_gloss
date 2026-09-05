"""Run one complete M01 centering test and optionally write a review board."""

import argparse
from itertools import product
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "KRT" / "py_router"))
sys.path.insert(0, str(ROOT))

from check_connected import check_net_connectivity  # noqa: E402
from dgloss.interpad import (center_across_branch_doors,
                             center_across_multiple_doors,
                             center_with_sliding_neighbors,
                             door_crossing_direction,
                             door_crossing_options,
                             find_interpad_doors)  # noqa: E402
from dgloss.krt_clearance import KrtClearanceAdapter  # noqa: E402
from kicad_parser import parse_kicad_pcb  # noqa: E402
from kicad_writer import (generate_segment_sexpr,
                          remove_segments_from_content)  # noqa: E402
from kicad_krt_gloss.debug_overlay import write_cli_debug_overlay  # noqa: E402
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
    parser.add_argument("--proximity-mm", type=float, default=1.0,
                        help="absolute obstacle proximity in millimetres")
    parser.add_argument("--build-new-segments", action="store_true",
                        help="allow centering to increase the segment count")
    parser.add_argument("--build-multi-door-path", action="store_true",
                        help="allow one path to center across multiple doors")
    parser.add_argument("--rules-board", type=Path,
                        help="source board whose project rules apply to this staged test")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--debug-layer", default="auto",
                        choices=("auto",) + tuple(
                            f"User.{index}" for index in range(1, 10)))
    args = parser.parse_args()

    pcb = parse_kicad_pcb(str(args.board))
    rules_board = args.rules_board or args.board
    config = _config(rules_board, pcb)
    net_id = next((nid for nid, net in pcb.nets.items()
                   if net.name == args.net), None)
    if net_id is None:
        raise SystemExit(f"unknown net: {args.net}")

    scan = find_interpad_doors(
        pcb, config, net_id=net_id,
        proximity_mm=args.proximity_mm)
    ranked_doors = sorted(scan.doors, key=lambda item: abs(item.offset),
                          reverse=True)
    current = [segment for segment in pcb.segments if segment.net_id == net_id]
    vias = [via for via in pcb.vias if via.net_id == net_id]
    pads = pcb.pads_by_net.get(net_id, [])
    adapter = KrtClearanceAdapter(pcb, config)
    checked = perf_counter()
    before_grade = check_net_connectivity(
        net_id, current, vias, pads, [], pcb_data=pcb)
    validation_ms = (perf_counter() - checked) * 1000.0
    construction_ms = scan.elapsed_ms
    candidates_tested = 0
    selected_doors = candidate = after_grade = None
    clearance_ok = connectivity_ok = False
    proposals = []
    if args.build_multi_door_path:
        if len(ranked_doors) >= 2:
            branch_doors = tuple(ranked_doors)
            option_sets = [door_crossing_options(
                door, allow_reorientation=args.build_new_segments)
                for door in branch_doors]
            combinations = list(product(*[range(len(options))
                                           for options in option_sets]))
            combinations.sort(key=lambda indices: (sum(indices), indices))
            for indices in combinations[:64]:
                directions = {id(door): option_sets[index][choice]
                              for index, (door, choice) in enumerate(
                                  zip(branch_doors, indices))}
                proposals.append((branch_doors, "branch", directions))
        groups = {}
        for proposed_door in ranked_doors:
            groups.setdefault(id(proposed_door.segment), []).append(
                proposed_door)
        multi_groups = [tuple(group) for group in groups.values()
                        if len(group) >= 2]
        multi_groups.sort(key=lambda group:
                          (len(group), sum(abs(item.offset)
                                           for item in group)), reverse=True)
        proposals.extend((group, "segment", None) for group in multi_groups)
    proposals.extend(((proposed_door,), "single", None)
                     for proposed_door in ranked_doors)
    selected_directions = None
    for proposed_doors, proposal_kind, proposed_directions in proposals:
        building = perf_counter()
        if proposal_kind == "branch":
            proposed_candidate = center_across_branch_doors(
                pcb, proposed_doors,
                build_new_segments=args.build_new_segments,
                crossing_directions=proposed_directions)
        elif proposal_kind == "segment":
            proposed_candidate = center_across_multiple_doors(
                pcb, proposed_doors,
                build_new_segments=args.build_new_segments)
        else:
            proposed_candidate = center_with_sliding_neighbors(
                pcb, proposed_doors[0],
                build_new_segments=args.build_new_segments)
        construction_ms += (perf_counter() - building) * 1000.0
        if proposed_candidate is None:
            continue
        candidates_tested += 1
        source_ids = {id(segment)
                      for segment in proposed_candidate.source_segments}
        trial = [segment for segment in current
                 if id(segment) not in source_ids] + \
                list(proposed_candidate.segments)
        checked = perf_counter()
        proposed_clearance_ok = adapter.connector_clears(
            proposed_candidate.segments)
        proposed_after_grade = check_net_connectivity(
            net_id, trial, vias, pads, [], pcb_data=pcb)
        proposed_connectivity_ok = (
            not before_grade.get("connected") or
            proposed_after_grade.get("connected")) and \
            len(proposed_after_grade.get("disconnected_pads") or []) <= \
            len(before_grade.get("disconnected_pads") or []) and \
            (proposed_after_grade.get("num_components") or 1) <= \
            (before_grade.get("num_components") or 1)
        validation_ms += (perf_counter() - checked) * 1000.0
        if proposed_clearance_ok and proposed_connectivity_ok:
            selected_doors, candidate = proposed_doors, proposed_candidate
            selected_directions = proposed_directions
            clearance_ok = proposed_clearance_ok
            connectivity_ok = proposed_connectivity_ok
            after_grade = proposed_after_grade
            break
    if candidate is None:
        raise SystemExit("no complete valid sliding candidate")

    def grade_summary(grade):
        return {
            "connected": bool(grade.get("connected")),
            "num_components": grade.get("num_components"),
            "disconnected_pad_count": len(grade.get("disconnected_pads") or []),
        }

    result = {
        "board": str(args.board.resolve()),
        "rules_board": str(rules_board.resolve()),
        "net": args.net,
        "proximity_mm": args.proximity_mm,
        "build_new_segments": args.build_new_segments,
        "build_multi_door_path": args.build_multi_door_path,
        "centering_scope": ("branch" if len({id(door.segment)
                                              for door in selected_doors}) > 1
                             else "segment"),
        "candidates_tested": candidates_tested,
        "doors": [{
            "pads": [f"{door.pad_a.component_ref}.{door.pad_a.pad_number}",
                     f"{door.pad_b.component_ref}.{door.pad_b.pad_number}"],
            "proximity_mm": round(door.proximity_mm, 6),
            "obstacle_distances_to_segment_mm": [
                round(door.distance_a, 6), round(door.distance_b, 6)],
            "axis": list(door.axis),
            "original_crossing": list(door.crossing),
            "selected_orientation_degrees": round(
                math.degrees(math.atan2(*reversed(
                    ((selected_directions or {}).get(id(door)) or
                     door_crossing_direction(
                         door, allow_reorientation=False))))) %
                180.0, 6),
        } for door in selected_doors],
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
    if not clearance_ok or not connectivity_ok:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        raise SystemExit(2)

    if args.output:
        source = args.board.resolve()
        output = args.output.resolve()
        if source == output:
            raise SystemExit("output must differ from the source board")
        content = source.read_text(encoding="utf-8")
        net_names = {nid: net.name for nid, net in pcb.nets.items()}
        content, removed = remove_segments_from_content(
            content, list(candidate.source_segments), net_names)
        if removed != len(candidate.source_segments):
            raise SystemExit(
                f"removed {removed}/{len(candidate.source_segments)} source segments")
        additions = "\n".join(generate_segment_sexpr(
            (segment.start_x, segment.start_y),
            (segment.end_x, segment.end_y), segment.width, segment.layer,
            segment.net_id, net_names.get(segment.net_id))
            for segment in candidate.segments)
        final_paren = content.rfind(")")
        content = content[:final_paren] + "\n" + additions + "\n" + \
            content[final_paren:]
        output.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=".interpad_", suffix=".kicad_pcb", dir=output.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as sink:
                sink.write(content)
            os.replace(temporary, output)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

        changes = {
            "segments": ([{"old": segment, "new": None}
                          for segment in candidate.source_segments] +
                         [{"old": None, "new": segment}
                          for segment in candidate.segments]),
            "vias": [],
            "doors": list(selected_doors),
        }
        debug_layer = write_cli_debug_overlay(
            str(output), changes, args.debug_layer)
        result["output"] = str(output)
        result["debug_layer"] = debug_layer
        result["door_marker_style"] = "dash_dot"

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
