"""Read-only Centering acceptance on the modified test_centering2 /A board."""
import hashlib
import argparse
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import reproduce_corridor_fold as native
from dgloss.pipeline import run_centering


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--replay-before', action='store_true',
                        help='Replay the recorded pre-Centering /A chain on a detached board')
    args = parser.parse_args()
    source = args.board.resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    board = native.pcbnew.LoadBoard(str(source))
    data = native.build_pcb_data_from_board(board)
    net = next(n for n, value in data.nets.items() if value.name == '/A')
    config = native.build_krt_config(board, data, .1, net_ids={net})
    if args.replay_before:
        # Recorded User.1 input geometry, not a claim that the saved PCB is
        # still the original snapshot. Only the detached native board changes.
        from dgloss.chain_topology import _simple_chains
        chain = next(c for c in _simple_chains(data, net) if (153.1, 83.6) in c.points)
        keys = {frozenset(((round(s.start_x*1e6), round(s.start_y*1e6)),
                          (round(s.end_x*1e6), round(s.end_y*1e6)))) for s in chain.segments}
        tracks = []
        for track in board.GetTracks():
            a, b = track.GetStart(), track.GetEnd()
            if track.GetNetCode() == net and frozenset(((a.x, a.y), (b.x, b.y))) in keys:
                tracks.append(track)
        points = [(153.1, 83.6), (149.875033, 86.824967), (149.875033, 88.945533),
                  (151.374499, 90.445), (158.265, 90.445), (159.705, 91.885)]
        assert len(tracks) == len(points)-1
        for track, a, b in zip(tracks, points, points[1:]):
            track.SetStart(native.pcbnew.VECTOR2I(*(round(v*1e6) for v in a)))
            track.SetEnd(native.pcbnew.VECTOR2I(*(round(v*1e6) for v in b)))
            track.SetWidth(round(chain.width*1e6))
            track.SetLayer(native.pcbnew.F_Cu)
            track.SetNetCode(net)
        data = native.build_pcb_data_from_board(board)
        config = native.build_krt_config(board, data, .1, net_ids={net})
    results = []
    outcome = run_centering(results, data, config, net_ids=[net], proximity_mm=2.54)
    assert outcome.stats.get('g5_valid')
    assert outcome.stats['doors_centered'] + outcome.stats.get('doors_already_centered', 0) == 1
    applied = native.apply_gloss(board, results, outcome)
    crossings = []
    for track in board.GetTracks():
        if track.GetNetCode() != net:
            continue
        a, b = track.GetStart(), track.GetEnd()
        dx, dy = abs(b.x-a.x), abs(b.y-a.y)
        assert min(dx, dy, abs(dx-dy)) <= 1
        if a.y == b.y and min(a.x, b.x) < 152085000 < max(a.x, b.x):
            crossings.append(a.y)
    assert crossings == [90615000]
    assert native.acute_joints([s for s in data.segments if s.net_id == net]) == 0
    # Verify the actual native chain: sliding preserves the diagonal approach,
    # including the joints, rather than checking only per-segment directions.
    from dgloss.chain_topology import _simple_chains
    actual = native.build_pcb_data_from_board(board)
    chain = next(c for c in _simple_chains(actual, net) if (153.1, 83.6) in c.points)
    assert len(chain.segments) == 5
    for a, b, c in zip(chain.points, chain.points[1:], chain.points[2:]):
        u, v = (b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1])
        assert (u[0]*v[0]+u[1]*v[1]) / (math.hypot(*u)*math.hypot(*v)) >= math.sqrt(.5)-1e-6
    if args.replay_before:
        assert any(math.dist(p, (149.875033, 89.115533)) <= 1e-6 for p in chain.points)
    diagonal = next(s for s in chain.segments
                    if 89 < min(s.start_y, s.end_y) < 90 and
                    abs(s.end_x-s.start_x) > 1)
    expected = frozenset(((round(diagonal.start_x*1e6), round(diagonal.start_y*1e6)),
                          (round(diagonal.end_x*1e6), round(diagonal.end_y*1e6))))
    assert any(shape.GetLayer() == native.pcbnew.User_1 and
               frozenset(((shape.GetStart().x, shape.GetStart().y),
                          (shape.GetEnd().x, shape.GetEnd().y))) == expected
               for shape in board.GetDrawings())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    print(json.dumps(dict(sha256=digest, source_unchanged=True, replay_before=args.replay_before,
                         native_chain=chain.points, applied=applied,
                         native_crossing_y_mm=crossings[0]/1e6,
                         stats=outcome.stats), indent=2))


if __name__ == '__main__':
    main()
