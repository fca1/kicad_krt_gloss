from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "KRT", ROOT / "KRT" / "py_router",
             ROOT / "KRT" / "rust_router"):
    sys.path.insert(0, str(path))

from kicad_parser import Pad, Segment
from routing_config import GridRouteConfig

from dgloss.interpad import center_with_sliding_neighbors, find_interpad_doors


def _pad(ref, x, y, net_id, size=1.0):
    return Pad(ref, "1", x, y, 0.0, 0.0, size, size, "circle",
               ["F.Cu"], net_id, ref)


def _pcb(segments):
    pads = {2: [_pad("A", 0.0, 0.0, 2)],
            3: [_pad("B", 3.0, 0.0, 3)]}
    return SimpleNamespace(
        segments=segments, pads_by_net=pads,
        board_info=SimpleNamespace(copper_layers=["F.Cu"]),
        nets={1: SimpleNamespace(name="TARGET")})


def test_finds_one_weighted_door():
    segment = Segment(1.2, -2.0, 1.2, 2.0, 0.2, "F.Cu", 1)
    pcb = _pcb([segment])
    config = GridRouteConfig(
        clearance=0.2, layers=["F.Cu"], net_clearances={3: 0.4})

    scan = find_interpad_doors(pcb, config)

    assert len(scan.doors) == 1
    door = scan.doors[0]
    assert round(door.copper_gap, 6) == 2.0
    assert round(door.admissible_width, 6) == 1.4
    assert round(door.axis[0], 6) == 1.4
    assert round(door.offset, 6) == 0.2


def test_rejects_a_gate_crossed_by_two_tracks():
    pcb = _pcb([
        Segment(1.2, -2.0, 1.2, 2.0, 0.2, "F.Cu", 1),
        Segment(1.8, -2.0, 1.8, 2.0, 0.2, "F.Cu", 4),
    ])
    config = GridRouteConfig(clearance=0.2, layers=["F.Cu"])

    assert find_interpad_doors(pcb, config).doors == ()


def test_counts_a_second_track_ending_inside_the_gate():
    pcb = _pcb([
        Segment(1.2, -2.0, 1.2, 2.0, 0.2, "F.Cu", 1),
        Segment(1.8, 0.0, 1.8, 1.0, 0.2, "F.Cu", 4),
    ])
    config = GridRouteConfig(clearance=0.2, layers=["F.Cu"])

    assert find_interpad_doors(pcb, config).doors == ()


def test_centers_a_diagonal_by_sliding_on_parallel_rails():
    first = Segment(0.0, 2.0, 0.0, 1.0, 0.2, "F.Cu", 1)
    diagonal = Segment(0.0, 1.0, 1.0, 0.0, 0.2, "F.Cu", 1)
    last = Segment(1.0, 0.0, 1.0, -2.0, 0.2, "F.Cu", 1)
    pcb = SimpleNamespace(segments=[first, diagonal, last])
    door = SimpleNamespace(segment=diagonal, axis=(0.5, 1.0),
                           crossing=(0.5, 0.5))

    candidate = center_with_sliding_neighbors(pcb, door)

    assert candidate is not None
    assert candidate.translation == (0.0, 0.5)
    assert len(candidate.source_segments) == 3
    assert len(candidate.segments) == 3
    assert (candidate.segments[1].start_x,
            candidate.segments[1].start_y) == (0.0, 1.5)
    assert (candidate.segments[1].end_x,
            candidate.segments[1].end_y) == (1.0, 0.5)
