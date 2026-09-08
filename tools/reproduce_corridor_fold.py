"""Read-only native regression for the saved /A fold; run with KiCad Python.

No SaveBoard, GUI action, timer or modification of the source PCB.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'kicad_krt_gloss'))
import runtime
runtime.configure_krt_runtime()
# Import the native adapter without executing the ActionPlugin registration.
package = types.ModuleType('_corridor_probe')
package.__path__ = [str(ROOT / 'kicad_krt_gloss')]
sys.modules[package.__name__] = package
from _corridor_probe.board_adapter import build_krt_config
import pcbnew
from dgloss.krt_api import build_pcb_data_from_board, calculate_route_length
from dgloss.config import GlossConfig
from dgloss.pipeline import run_final_gloss


def overlap_pairs(segments):
    count = 0
    for i, first in enumerate(segments):
        dx, dy = first.end_x-first.start_x, first.end_y-first.start_y
        length = math.hypot(dx, dy)
        if not length:
            continue
        ux, uy = dx/length, dy/length
        for second in segments[i+1:]:
            if first.layer != second.layer:
                continue
            offsets = [(second.start_x-first.start_x, second.start_y-first.start_y),
                       (second.end_x-first.start_x, second.end_y-first.start_y)]
            if all(abs(x*uy-y*ux) <= 1e-7 for x, y in offsets):
                low, high = sorted(x*ux+y*uy for x, y in offsets)
                count += min(length, high)-max(0, low) > 1e-7
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--net-id', type=int, default=7)
    args = parser.parse_args()
    fingerprint = hashlib.sha256(args.board.read_bytes()).hexdigest()
    board = pcbnew.LoadBoard(str(args.board.resolve()))
    pcb = build_pcb_data_from_board(board)
    config = build_krt_config(board, pcb, .1, net_ids={args.net_id})
    before = [s for s in pcb.segments if s.net_id == args.net_id]
    outcome = run_final_gloss([], pcb, config,
                             GlossConfig(stay_in_corridor=True, g4_max_passes=1),
                             net_ids={args.net_id})
    after = [s for s in pcb.segments if s.net_id == args.net_id]
    octolinear = all(min(abs(s.end_x-s.start_x), abs(s.end_y-s.start_y),
                        abs(abs(s.end_x-s.start_x)-abs(s.end_y-s.start_y))) <= 1e-7
                    for s in after)
    unchanged = fingerprint == hashlib.sha256(args.board.read_bytes()).hexdigest()
    report = dict(sha256=fingerprint, source_unchanged=unchanged,
                  before_mm=calculate_route_length(before),
                  after_mm=calculate_route_length(after),
                  before_segments=len(before), after_segments=len(after),
                  before_overlap_pairs=overlap_pairs(before),
                  after_overlap_pairs=overlap_pairs(after), octolinear=octolinear,
                  g5_valid=outcome.stats.get('g5_valid'),
                  connectivity_regressions=outcome.stats.get('connectivity_regressions'),
                  total_ms=outcome.stats.get('total_ms'))
    print(json.dumps(report, indent=2))
    assert unchanged and octolinear and report['g5_valid']
    assert report['connectivity_regressions'] == 0
    assert report['before_overlap_pairs'] > 0 and report['after_overlap_pairs'] == 0
    assert report['after_mm'] < report['before_mm']


if __name__ == '__main__':
    main()
