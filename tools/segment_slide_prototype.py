#!/usr/bin/env python3
"""Evaluate orientation-neutral three-segment slides without changing a PCB."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "KRT", ROOT / "KRT" / "py_router",
             ROOT / "KRT" / "rust_router"):
    sys.path.insert(0, str(path))

from check_connected import check_net_connectivity
from gloss import build_krt_config, build_parser as build_gloss_parser
from kicad_parser import Segment, board_uses_name_nets, parse_kicad_pcb
from kicad_writer import generate_segment_sexpr, remove_segments_from_content
from net_queries import calculate_route_length

from dgloss.algorithm import (_connectivity_worse, _simple_chains,
                              _touches_other_same_net)
from dgloss.context import build_gloss_context, resolve_gloss_scope
from dgloss.segment_sliding import slide_interval, slide_segment


def _segment_dict(segment):
    return {
        "start": [segment.start_x, segment.start_y],
        "end": [segment.end_x, segment.end_y],
        "width": segment.width,
        "layer": segment.layer,
        "net_id": segment.net_id,
    }


def _offsets(interval, step, span_limit):
    lower = max(interval.minimum, -span_limit)
    upper = min(interval.maximum, span_limit)
    first = math.ceil((lower - 1e-9) / step)
    last = math.floor((upper + 1e-9) / step)
    indices = [index for index in range(first, last + 1) if index]
    # Evaluate near the incumbent first, independently in both directions.
    return sorted(indices, key=lambda index: (abs(index), index))


def evaluate(board, config, net_ids, *, budget_seconds=30.0,
             max_offsets_per_triple=2000):
    context = build_gloss_context(board, config, net_ids)
    deadline = perf_counter() + budget_seconds
    best = None
    triples = offsets_tested = geometries_built = exact_clear = 0

    for net_id in net_ids:
        if perf_counter() >= deadline:
            break
        net_segments = [segment for segment in board.segments
                        if segment.net_id == net_id]
        net_vias = [via for via in board.vias if via.net_id == net_id]
        before_grade = check_net_connectivity(
            net_id, net_segments, net_vias,
            board.pads_by_net.get(net_id, []), [], pcb_data=board)
        for chain in _simple_chains(board, net_id):
            for index in range(1, len(chain.segments) - 1):
                if perf_counter() >= deadline:
                    break
                source = tuple(chain.segments[index - 1:index + 2])
                interval = slide_interval(
                    *source, minimum_length=context.coord.grid_step)
                if interval is None:
                    continue
                triples += 1
                span_limit = max(
                    calculate_route_length(source), context.coord.grid_step)
                indices = _offsets(
                    interval, context.coord.grid_step, span_limit)
                if len(indices) > max_offsets_per_triple:
                    indices = indices[:max_offsets_per_triple]
                source_ids = {id(segment) for segment in source}
                outside = [segment for segment in net_segments
                           if id(segment) not in source_ids]
                anchors = []
                for endpoint in (
                        (source[0].start_x, source[0].start_y),
                        (source[0].end_x, source[0].end_y),
                        (source[2].start_x, source[2].start_y),
                        (source[2].end_x, source[2].end_y)):
                    if not any(math.dist(endpoint, middle_endpoint) <= 1e-7
                               for middle_endpoint in (
                                   (source[1].start_x, source[1].start_y),
                                   (source[1].end_x, source[1].end_y))):
                        anchors.append(endpoint)
                if len(anchors) != 2:
                    continue

                for offset_index in indices:
                    if perf_counter() >= deadline:
                        break
                    offsets_tested += 1
                    candidate = slide_segment(
                        *source, offset_index * context.coord.grid_step,
                        minimum_length=context.coord.grid_step)
                    if candidate is None:
                        continue
                    geometries_built += 1
                    gain = candidate.before_length - candidate.after_length
                    if gain <= context.coord.grid_step + 1e-12:
                        continue
                    if _touches_other_same_net(
                            candidate.segments, outside, net_vias, anchors):
                        continue
                    if not context.clearance_adapter.connector_clears(
                            candidate.segments):
                        continue
                    exact_clear += 1
                    trial = outside + list(candidate.segments)
                    after_grade = check_net_connectivity(
                        net_id, trial, net_vias,
                        board.pads_by_net.get(net_id, []), [], pcb_data=board)
                    if _connectivity_worse(before_grade, after_grade):
                        continue
                    score = (-gain, abs(candidate.offset), index)
                    if best is None or score < best[0]:
                        best = score, net_id, candidate

    elapsed = (perf_counter() - (deadline - budget_seconds)) * 1000.0
    result = {
        "complete": perf_counter() < deadline,
        "elapsed_ms": round(elapsed, 3),
        "nets": len(net_ids),
        "triples": triples,
        "offsets_tested": offsets_tested,
        "geometries_built": geometries_built,
        "exact_clear": exact_clear,
        "best": None,
    }
    if best is not None:
        _score, net_id, candidate = best
        result["best"] = {
            "net_id": net_id,
            "net": board.nets[net_id].name,
            "offset": candidate.offset,
            "before_mm": candidate.before_length,
            "after_mm": candidate.after_length,
            "saved_mm": candidate.before_length - candidate.after_length,
            "source": [_segment_dict(segment)
                       for segment in candidate.source_segments],
            "candidate": [_segment_dict(segment)
                          for segment in candidate.segments],
        }
    return result


def write_candidate(input_path, output_path, board, best):
    """Publish one inspectable board copy containing the reported candidate."""
    source = best["source_segments"]
    candidate = best["segments"]
    content = input_path.read_text(encoding="utf-8")
    net_names = {net_id: net.name for net_id, net in board.nets.items()}
    content, removed = remove_segments_from_content(
        content, list(source), net_names)
    if removed != len(source):
        raise RuntimeError(
            f"refusing partial output: removed {removed}/{len(source)} segments")

    use_names = board_uses_name_nets(content)
    additions = "\n".join(generate_segment_sexpr(
        (segment.start_x, segment.start_y),
        (segment.end_x, segment.end_y),
        segment.width, segment.layer, segment.net_id,
        net_name=net_names[segment.net_id] if use_names else None)
        for segment in candidate)
    last_paren = content.rfind(")")
    if last_paren < 0:
        raise RuntimeError("input is not a KiCad s-expression")
    content = content[:last_paren] + "\n" + additions + "\n" + content[last_paren:]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".partial")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, output_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("--net", action="append", default=[])
    parser.add_argument("--budget-seconds", type=float, default=30.0)
    parser.add_argument("--grid-step", type=float, default=0.1)
    parser.add_argument("--output", type=Path,
                        help="write a copy containing the best candidate")
    args = parser.parse_args()

    board_path = str(args.board.resolve())
    board = parse_kicad_pcb(board_path)
    if args.net:
        wanted = set(args.net)
        requested = [net_id for net_id, net in board.nets.items()
                     if net.name in wanted]
        missing = wanted - {board.nets[net_id].name for net_id in requested}
        if missing:
            raise SystemExit("unknown net(s): " + ", ".join(sorted(missing)))
    else:
        requested = None
    net_ids, _excluded, _reasons = resolve_gloss_scope(board, requested)
    gloss_args = build_gloss_parser().parse_args([
        board_path, "--preview", "--grid-step", str(args.grid_step)])
    config = build_krt_config(gloss_args, board, net_ids)
    result = evaluate(
        board, config, net_ids, budget_seconds=args.budget_seconds)
    result["board"] = board_path
    if args.output is not None:
        if result["best"] is None:
            raise SystemExit("no candidate to write")
        best = result["best"]
        source = tuple(Segment(
            *item["start"], *item["end"], item["width"], item["layer"],
            item["net_id"]) for item in best["source"])
        candidate = tuple(Segment(
            *item["start"], *item["end"], item["width"], item["layer"],
            item["net_id"]) for item in best["candidate"])
        output_path = args.output.resolve()
        write_candidate(args.board.resolve(), output_path, board, {
            "source_segments": source,
            "segments": candidate,
        })
        result["output"] = str(output_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
