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
from kicad_krt_gloss.debug_overlay import door_lines


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


def test_centers_from_a_fixed_pad_with_one_sliding_neighbour():
    diagonal = Segment(4.0, 0.0, 2.0, 2.0, 0.2, "F.Cu", 1)
    last = Segment(2.0, 2.0, 0.0, 2.0, 0.2, "F.Cu", 1)
    fixed_pad = _pad("P", 4.0, 0.0, 1)
    pcb = SimpleNamespace(
        segments=[diagonal, last], pads_by_net={1: [fixed_pad]},
        board_info=SimpleNamespace(copper_layers=["F.Cu"]))
    door = SimpleNamespace(segment=diagonal, axis=(3.0, 0.8),
                           crossing=(3.0, 1.0))

    candidate = center_with_sliding_neighbors(pcb, door)

    assert candidate is not None
    assert len(candidate.source_segments) == 2
    assert len(candidate.segments) == 3
    assert (candidate.segments[0].start_x,
            candidate.segments[0].start_y) == (4.0, 0.0)
    assert all(segment.layer == "F.Cu" and segment.net_id == 1
               for segment in candidate.segments)


def test_fixed_source_segment_cannot_be_centered():
    diagonal = Segment(4.0, 0.0, 2.0, 2.0, 0.2, "F.Cu", 1,
                       locked=True)
    last = Segment(2.0, 2.0, 0.0, 2.0, 0.2, "F.Cu", 1)
    pcb = SimpleNamespace(
        segments=[diagonal, last], pads_by_net={1: [_pad("P", 4.0, 0.0, 1)]},
        board_info=SimpleNamespace(copper_layers=["F.Cu"]))
    door = SimpleNamespace(segment=diagonal, axis=(3.0, 0.8),
                           crossing=(3.0, 1.0))

    assert center_with_sliding_neighbors(pcb, door) is None


def test_applied_door_emits_one_debug_marker():
    door = SimpleNamespace(edge_a=(1.0, 2.0), edge_b=(3.0, 4.0))

    assert list(door_lines({"doors": [door]})) == [
        ((1.0, 2.0), (3.0, 4.0), 0.12)]
