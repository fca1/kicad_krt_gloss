"""Read-only regression probe for test_centering2 /C with 5 mm proximity."""

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import run_centering
from dgloss.interpad import InterpadCandidate, _segment_pad_distance
from dgloss.protected_centering import passage_constraints, respects_passages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board')
    args = parser.parse_args()
    cli = gloss.build_parser()
    options = cli.parse_args([args.board, '--nets', '/C'])
    pcb = gloss.parse_kicad_pcb(args.board)
    net_ids = [n for _, n in gloss.resolve_scope(cli, options, pcb)]
    config = gloss.build_krt_config(options, pcb, net_ids)
    before = [s for s in pcb.segments if s.net_id in net_ids]
    outcome = run_centering([], pcb, config, net_ids=net_ids,
        proximity_mm=5, build_new_segments=True, build_multi_door_path=True,
        budget_seconds=20, _emit_log=False)
    after = [s for s in pcb.segments if s.net_id in net_ids]
    stats = outcome.stats
    assert stats.get('g5_valid') and not stats['budget_expired']
    assert stats['doors_centered'] == 4
    assert stats['after_mm'] < 125, stats
    assert len(after) < 25
    candidate = InterpadCandidate(tuple(before), tuple(after), (0, 0), 0, 0)
    constraints = passage_constraints(candidate, outcome.changes['doors'])
    assert constraints is not None and respects_passages(after, constraints)
    pads = []
    for pad, required in constraints[1]:
        actual = min(_segment_pad_distance((s.start_x, s.start_y),
            (s.end_x, s.end_y), pad) - s.width / 2 for s in after)
        pads.append({'pad': pad.component_ref, 'required_mm': round(required, 6),
                     'actual_mm': round(actual, 6)})
    angles = []
    for door, direction in constraints[0]:
        gate = (door.edge_b[0] - door.edge_a[0], door.edge_b[1] - door.edge_a[1])
        cosine = abs(sum(direction[k] * gate[k] for k in (0, 1))) / math.hypot(*gate)
        angles.append({'pads': [door.pad_a.component_ref, door.pad_b.component_ref],
                       'angle_degrees': round(math.degrees(math.acos(min(1, cosine))), 3)})
    print(json.dumps({'before_mm': stats['before_mm'],
        'after_gloss_mm': round(stats['before_mm'] - stats['cleanup_saved_mm'], 4),
        'after_mm': stats['after_mm'], 'segments': len(after),
        'doors': stats['doors_centered'], 'g5_valid': stats['g5_valid'],
        'elapsed_ms': stats['total_ms'], 'pad_protection': pads,
        'crossing_angles': angles}, indent=2))


if __name__ == '__main__':
    main()
