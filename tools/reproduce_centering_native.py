"""Read-only Centering acceptance on the modified test_centering2 /A board."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import reproduce_corridor_fold as native
from dgloss.pipeline import run_centering


def main():
    source = Path(sys.argv[1]).resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    board = native.pcbnew.LoadBoard(str(source))
    data = native.build_pcb_data_from_board(board)
    net = next(n for n, value in data.nets.items() if value.name == '/A')
    config = native.build_krt_config(board, data, .1, net_ids={net})
    results = []
    outcome = run_centering(results, data, config, net_ids=[net], proximity_mm=2.54)
    assert outcome.stats.get('g5_valid') and outcome.stats['doors_centered'] == 1
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
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    print(json.dumps(dict(sha256=digest, source_unchanged=True, applied=applied,
                         native_crossing_y_mm=crossings[0]/1e6,
                         stats=outcome.stats), indent=2))


if __name__ == '__main__':
    main()
