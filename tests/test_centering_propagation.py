"""Centering extends existing rails; it does not substitute another route."""
import math
from types import SimpleNamespace
import pytest
from dgloss.krt_api import Segment
from dgloss.interpad_paths import center_with_propagated_neighbors


@pytest.mark.parametrize('angle', range(0, 360, 45))
@pytest.mark.parametrize('reflect', [1, -1])
@pytest.mark.parametrize('reverse', [False, True])
def test_shift_propagates_to_next_rail_preserving_directions(angle, reflect, reverse):
    co, si = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    def transform(p):
        x, y = p[0], reflect*p[1]
        return (co*x-si*y, si*x+co*y)
    points = [transform(p) for p in [(0, 0), (0, 2), (2, 4), (6, 4), (8, 6)]]
    segments = [Segment(*a, *b, .2, 'F.Cu', 1) for a, b in zip(points, points[1:])]
    source = segments[2]
    if reverse:
        segments = [Segment(s.end_x, s.end_y, s.start_x, s.start_y,
                            s.width, s.layer, s.net_id) for s in reversed(segments)]
        source = segments[1]
    pcb = SimpleNamespace(segments=segments, vias=[], pads_by_net={})
    door = SimpleNamespace(segment=source, crossing=transform((4, 4)), axis=transform((4, 4.5)))
    candidates = list(center_with_propagated_neighbors(pcb, door))
    assert len(candidates) == 1
    candidate = candidates[0]
    expected = [transform(p) for p in [(0, 0), (0, 2.5), (2, 4.5), (6.5, 4.5), (8, 6)]]
    got = {(round(s.start_x, 7), round(s.start_y, 7)) for s in candidate.segments}
    got.update((round(s.end_x, 7), round(s.end_y, 7)) for s in candidate.segments)
    assert got == {(round(x, 7), round(y, 7)) for x, y in expected}
    assert len(candidate.segments) == len(segments)
    assert pcb.segments is segments
    assert not list(center_with_propagated_neighbors(pcb, door, deadline=-1))


def test_propagation_stops_at_locked_rail():
    points = [(0, 0), (0, 2), (2, 4), (6, 4), (8, 6)]
    segments = [Segment(*a, *b, .2, 'F.Cu', 1) for a, b in zip(points, points[1:])]
    segments[0].locked = True
    pcb = SimpleNamespace(segments=segments, vias=[], pads_by_net={})
    door = SimpleNamespace(segment=segments[2], crossing=(4, 4), axis=(4, 4.5))
    assert not list(center_with_propagated_neighbors(pcb, door))
