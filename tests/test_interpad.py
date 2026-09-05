from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "KRT", ROOT / "KRT" / "py_router",
             ROOT / "KRT" / "rust_router"):
    sys.path.insert(0, str(path))

from kicad_parser import Pad, Segment
from routing_config import GridRouteConfig

from dgloss.interpad import find_interpad_doors


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
