"""Additional clearances belong to the whole replacement, including connectors."""

from types import SimpleNamespace
import math

import pytest

from test_interpad import _pad
from kicad_parser import Segment
from dgloss.interpad import InterpadCandidate, _segment_pad_distance
from dgloss.protected_centering import passage_constraints, respects_passages
from dgloss.protected_centering import build_protected_path


def test_obsolete_centering_settings_are_ignored_on_load():
    from dgloss.config import GlossConfig

    config = GlossConfig.from_value({
        'centering_proximity_mm': 5.0,
        'centering_build_new_segments': False,
        'centering_build_multi_door_path': False,
    }).as_dict()
    assert config['centering_proximity_mm'] == 5.0
    assert 'centering_build_new_segments' not in config
    assert 'centering_build_multi_door_path' not in config


def test_finite_distance_uses_copper_edges():
    pad = _pad('P', 0, 0, 2, size=1)
    assert _segment_pad_distance((2, -3), (2, 3), pad) == pytest.approx(1.5, abs=2e-4)


def test_connector_cannot_spend_acquired_clearance():
    pad = _pad('P', 0, 0, 2, size=1)
    protected = ((), ((pad, 1.4),))
    centered = Segment(2, -3, 2, 3, .2, 'F.Cu', 1)
    connector = Segment(2, 3, .8, 1.8, .2, 'F.Cu', 1)
    assert respects_passages([centered], protected)
    assert not respects_passages([centered, connector], protected)


def test_shared_obstacle_uses_minimum_acquired_distance():
    shared = _pad('P', 0, 0, 2, size=1)
    other_a = _pad('A', 4, 0, 3, size=1)
    other_b = _pad('B', 6, 2, 4, size=1)
    first = Segment(2, -1, 2, 1, .2, 'F.Cu', 1)
    second = Segment(3, 1.5, 3, 3, .2, 'F.Cu', 1)
    doors = [SimpleNamespace(edge_a=(.5, 0), edge_b=(3.5, 0),
                             axis=(2, 0), pad_a=shared, pad_b=other_a,
                             clearance_a=.2, clearance_b=.2, segment=first),
             SimpleNamespace(edge_a=(.5, 2), edge_b=(5.5, 2),
                             axis=(3, 2), pad_a=shared, pad_b=other_b,
                             clearance_a=.2, clearance_b=.2, segment=second)]
    candidate = InterpadCandidate((first, second), (first, second), (0, 0), 0, 0)
    constraints = passage_constraints(candidate, doors)
    distance = next(value for pad, value in constraints[1] if pad is shared)
    assert distance == pytest.approx(1.4, abs=2e-4)


def test_center_must_keep_crossing_direction():
    door = SimpleNamespace(edge_a=(-1, 0), edge_b=(1, 0), axis=(0, 0))
    constraint = (((door, (0, 1)),), ())
    assert respects_passages([Segment(0, -2, 0, 2, .2, 'F.Cu', 1)], constraint)
    assert not respects_passages([Segment(-2, -2, 2, 2, .2, 'F.Cu', 1)], constraint)


@pytest.mark.parametrize('angle', [0, 45, 90])
def test_finite_passages_keep_a_straight_route_under_rotation(angle):
    radians = math.radians(angle)

    def rotate(x, y):
        return (x * math.cos(radians) - y * math.sin(radians),
                x * math.sin(radians) + y * math.cos(radians))

    segments = [Segment(*rotate(0, 0), *rotate(10, 0), .2, 'F.Cu', 1),
                Segment(*rotate(10, 0), *rotate(20, 0), .2, 'F.Cu', 1)]
    doors = []
    for i, x in enumerate((6, 14)):
        a, b = _pad('A', *rotate(x, -2), 2), _pad('B', *rotate(x, 2), 3)
        doors.append(SimpleNamespace(segment=segments[i],
            axis=rotate(x, 0), crossing=rotate(x, 0),
            edge_a=rotate(x, -1.5), edge_b=rotate(x, 1.5),
            pad_a=a, pad_b=b, clearance_a=.2, clearance_b=.2))
    pcb = SimpleNamespace(segments=segments, vias=[], pads_by_net={})
    context = SimpleNamespace(pcb_data=pcb, coord=SimpleNamespace(grid_step=.1),
        segments_editable=lambda items: True,
        clearance_adapter=SimpleNamespace(connector_clears=lambda items: True))
    candidate = build_protected_path(context, doors)
    assert candidate is not None
    assert candidate.after_length == pytest.approx(20)
    assert respects_passages(candidate.segments, passage_constraints(candidate, doors))
    assert pcb.segments is segments
    assert build_protected_path(context, doors, deadline=-1) is None
