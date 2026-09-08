"""Centre spacing, native precision and regulatory approach clearance."""
from types import SimpleNamespace
import pytest
from test_interpad import _pad, _pcb
from dgloss.krt_api import Segment, GridRouteConfig
from dgloss.interpad import find_interpad_doors, InterpadCandidate
from dgloss.interpad_geometry import _native_direction, _octolinear
from dgloss.protected_centering import passage_constraints, respects_passages


@pytest.mark.parametrize('distance,expected', [(2.539999, 1), (2.54, 1), (2.540001, 0), (5.08, 0)])
def test_proxi_is_inclusive_centre_distance(distance, expected):
    pcb = _pcb([Segment(1.2, -2., 1.2, 2., .2, 'F.Cu', 1)])
    pcb.pads_by_net[3][0].global_x = distance
    assert len(find_interpad_doors(pcb, GridRouteConfig(clearance=.2, layers=['F.Cu']),
                                   proximity_mm=2.54).doors) == expected


@pytest.mark.parametrize('sx,sy', [(1, 1), (-1, 1), (1, -1), (-1, -1)])
def test_native_precision_does_not_weaken_output(sx, sy):
    a = (149.875033, 88.945533)
    b = (a[0]+sx*1.499466, a[1]+sy*1.499467)
    assert _native_direction(a, b) == (sx, sy)
    assert not _octolinear(a, b)
    assert _native_direction(a, (a[0]+sx*1.499466, a[1]+sy*1.499469)) is None


def test_approach_can_be_closer_than_center_but_not_violate_clearance():
    pad, other = _pad('A', 0, 0, 2), _pad('B', 4, 0, 3)
    crossing = Segment(2, -1, 2, 1, .2, 'F.Cu', 1)
    door = SimpleNamespace(edge_a=(.5, 0), edge_b=(3.5, 0), axis=(2, 0),
                           pad_a=pad, pad_b=other, clearance_a=.2, clearance_b=.2,
                           segment=crossing)
    candidate = InterpadCandidate((crossing,), (crossing,), (0, 0), 0, 0)
    constraints = passage_constraints(candidate, [door])
    approach = Segment(.9, -2, .9, -.5, .2, 'F.Cu', 1)
    assert respects_passages([approach, crossing], constraints)
    collision = Segment(.6, -2, .6, 0, .2, 'F.Cu', 1)
    assert not respects_passages([collision, crossing], constraints)
