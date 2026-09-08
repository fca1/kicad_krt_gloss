"""Audit detailed PACK0 snapshots without modifying any PCB source.

Reports length differences and rechecks old/new generated copper with the
current KRT adapter. A successful historic G5 is not an octolinearity proof.
"""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import gloss
    from kicad_parser import Segment, Via
    from dgloss.krt_clearance import (KrtClearanceAdapter,
        _exact_foreign_segment_distance, _exact_foreign_hole_distance)
    from dgloss.krt_api import FP_EPS_MM
    pack = json.loads((root / 'docs/PACK0.json').read_text())
    before = {r['board']: r for r in json.loads(args.before.read_text())}
    after = json.loads(args.after.read_text())

    def uncovered(seg, initial):
        dx, dy = seg.end_x-seg.start_x, seg.end_y-seg.start_y
        length = math.hypot(dx, dy)
        if length <= FP_EPS_MM:
            return [seg]
        ux, uy = dx/length, dy/length
        intervals = []
        for old in initial:
            if (old.net_id, old.layer, old.width) != (seg.net_id, seg.layer, seg.width):
                continue
            offsets = [(old.start_x-seg.start_x, old.start_y-seg.start_y),
                       (old.end_x-seg.start_x, old.end_y-seg.start_y)]
            if all(abs(x*uy-y*ux) <= FP_EPS_MM for x, y in offsets):
                lo, hi = sorted(x*ux+y*uy for x, y in offsets)
                if hi >= 0. and lo <= length:
                    intervals.append((max(0., lo), min(length, hi)))
        cursor = 0.
        gaps = []
        for lo, hi in sorted(intervals) + [(length, length)]:
            if lo > cursor + FP_EPS_MM:
                gaps.append((cursor, lo))
            cursor = max(cursor, hi)
        return [Segment(seg.start_x+ux*lo, seg.start_y+uy*lo,
                        seg.start_x+ux*hi, seg.start_y+uy*hi,
                        seg.width, seg.layer, seg.net_id) for lo, hi in gaps]

    def audit(row):
        entry = next(e for e in pack['boards'] if e['name'] == row['board'])
        board = Path(pack['corpus_root']) / entry['path']
        assert hashlib.sha256(board.read_bytes()).hexdigest() == row['sha256'] == entry['sha256']
        with redirect_stdout(io.StringIO()):
            pcb = gloss.parse_kicad_pcb(str(board))
            ids = [n['net_id'] for n in row['per_net_geometry']]
            cfg = gloss.build_krt_config(gloss.build_parser().parse_args(
                [str(board), '--preview']), pcb, ids)
        # Preserve out-of-scope objects; rebuild only the snapshot's routed nets.
        pcb.segments = [s for s in pcb.segments if s.net_id not in ids]
        pcb.vias = [v for v in pcb.vias if v.net_id not in ids]
        generated = []
        initial = []
        for net in row['per_net_geometry']:
            for layer, a, b, width, graphic, locked in net['before'][0]:
                initial.append(Segment(*a, *b, width, layer, net['net_id']))
            for signature in net['after'][0]:
                layer, a, b, width, graphic, locked = signature
                seg = Segment(*a, *b, width, layer, net['net_id'],
                              graphic=graphic, locked=locked)
                pcb.segments.append(seg)
                if signature not in net['before'][0]:
                    generated.append(seg)
            for x, y, size, drill, layers, free, locked, tenting in net['after'][1]:
                pcb.vias.append(Via(x, y, size, drill, layers, net['net_id'],
                                    free=free, locked=locked, tenting_attrs=dict(tenting)))
        adapter = KrtClearanceAdapter(pcb, cfg)
        failures = Counter()
        inherited = Counter()
        failure_details = []
        with adapter.stable_copper():
            for seg in generated:
                if not adapter.segment_clears(seg):
                    pieces = uncovered(seg, initial)
                    if all(adapter.segment_clears(s) for s in pieces):
                        inherited[seg.net_id] += 1
                    else:
                        failures[seg.net_id] += 1
                        reverse = Segment(seg.end_x, seg.end_y, seg.start_x, seg.start_y,
                                          seg.width, seg.layer, seg.net_id)
                        failure_details.append(dict(net=seg.net_id,
                            start=[seg.start_x, seg.start_y], end=[seg.end_x, seg.end_y],
                            reverse_clears=adapter.segment_clears(reverse),
                            effective=adapter._effective_clearance(seg.net_id, seg.layer),
                            width=seg.width, layer=seg.layer,
                            pad=adapter._pad_distance(seg.net_id, seg.start_x, seg.start_y,
                                seg.end_x, seg.end_y, seg.layer,
                                adapter._effective_clearance(seg.net_id, seg.layer), seg.width/2),
                            copper=_exact_foreign_segment_distance(pcb, seg.net_id,
                                seg.start_x, seg.start_y, seg.end_x, seg.end_y, seg.layer,
                                base_clearance=adapter._effective_clearance(seg.net_id, seg.layer),
                                net_clearances=adapter.net_clearances, track_clearances=adapter.track_clearances),
                            hole=_exact_foreign_hole_distance(pcb, seg.net_id,
                                seg.start_x, seg.start_y, seg.end_x, seg.end_y, adapter.npth_clearance),
                            edge=adapter._edge_clears(seg), keepout=adapter._keepouts_clear(seg)))
        assert hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
        return failures, inherited, failure_details

    comparisons = []
    for current in after:
        if current['board'] not in before:
            continue
        old = before[current['board']]
        (old_bad, old_inherited, _), (new_bad, new_inherited, new_details) = audit(old), audit(current)
        old_nets = {n['net_id']: n for n in old['per_net_geometry']}
        comparisons.append(dict(
            board=current['board'], before_saved_mm=old['saved_mm'],
            after_saved_mm=current['saved_mm'],
            before_new_non_octolinear=old['new_non_octolinear'],
            after_new_non_octolinear=current['new_non_octolinear'],
            before_clearance_rejected=dict(old_bad), after_clearance_rejected=dict(new_bad),
            before_inherited_clearance=dict(old_inherited), after_inherited_clearance=dict(new_inherited),
            after_clearance_details=new_details,
            losses=[dict(net_id=n['net_id'], label=n['label'],
                         extra_length_mm=n['after_mm']-old_nets[n['net_id']]['after_mm'],
                         before_new_non_octolinear=sum(d['net'] == n['net_id'] for d in old['non_octolinear_details']),
                         before_clearance_rejected=old_bad[n['net_id']])
                    for n in current['per_net_geometry']
                    if n['after_mm']-old_nets[n['net_id']]['after_mm'] > .001]))
    args.output.write_text(json.dumps(comparisons, indent=2), encoding='utf-8')
    print(json.dumps(comparisons, indent=2))


if __name__ == '__main__':
    main()
