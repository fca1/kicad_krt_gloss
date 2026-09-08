import math
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "KRT", ROOT / "KRT" / "py_router",
             ROOT / "KRT" / "rust_router"):
    sys.path.insert(0, str(path))

from kicad_parser import Segment
from dgloss.krt_api import calculate_route_length

from dgloss.algorithm import _reachable_segment_slides
from dgloss.segment_sliding import slide_interval, slide_segment, slide_length_rate


def _segment(a, b):
    return Segment(*a, *b, 0.4, "F.Cu", 1)


def _rotate(point, turns=1):
    angle = turns * math.pi / 4.0
    cosine, sine = math.cos(angle), math.sin(angle)
    return (point[0] * cosine - point[1] * sine,
            point[0] * sine + point[1] * cosine)


def _rotate_segment(segment, turns=1):
    return _segment(_rotate((segment.start_x, segment.start_y), turns),
                    _rotate((segment.end_x, segment.end_y), turns))


def _reflect(point):
    return (-point[0], point[1])


def _reflect_segment(segment):
    return _segment(_reflect((segment.start_x, segment.start_y)),
                    _reflect((segment.end_x, segment.end_y)))


def _points(slide):
    return [
        (slide.segments[0].start_x, slide.segments[0].start_y),
        *[(segment.end_x, segment.end_y) for segment in slide.segments],
    ]


def test_slides_horizontal_member_between_opposed_diagonals():
    first = _segment((86.3, 92.5), (92.4, 86.4))
    middle = _segment((92.4, 86.4), (132.3, 86.4))
    last = _segment((132.3, 86.4), (141.2, 95.3))

    candidate = slide_segment(first, middle, last, 3.2)

    assert candidate is not None
    expected = [(86.3, 92.5), (89.2, 89.6), (135.5, 89.6), (141.2, 95.3)]
    assert all(math.dist(a, b) < 1e-9 for a, b in zip(_points(candidate), expected))
    assert math.isclose(candidate.before_length, 61.11320343559642)
    assert math.isclose(candidate.after_length, 58.46223663640862)


def test_parallel_neighbours_keep_total_length_but_remain_constructible():
    first = _segment((0.0, 0.0), (4.0, 0.0))
    middle = _segment((4.0, 0.0), (6.0, 2.0))
    last = _segment((6.0, 2.0), (10.0, 2.0))

    candidate = slide_segment(first, middle, last, -1.25)

    assert candidate is not None
    assert math.isclose(candidate.before_length, candidate.after_length,
                        abs_tol=1e-6)
    expected = [(0., 0.), (4+1.25*math.sqrt(2), 0.),
                (6+1.25*math.sqrt(2), 2.), (10., 2.)]
    assert all(math.dist(a, b) < 1e-9 for a, b in zip(_points(candidate), expected))


def test_opposite_parallel_traversal_changes_both_outer_lengths_together():
    first = _segment((0.0, 0.0), (4.0, 0.0))
    middle = _segment((4.0, 0.0), (4.0, 2.0))
    last = _segment((4.0, 2.0), (1.0, 2.0))

    candidate = slide_segment(first, middle, last, 1.0)

    assert candidate is not None
    assert math.isclose(candidate.before_length - candidate.after_length, 2.0)


def test_slide_geometry_commutes_with_every_45_degree_rotation():
    source = (
        _segment((0.0, 0.0), (3.0, -3.0)),
        _segment((3.0, -3.0), (8.0, -3.0)),
        _segment((8.0, -3.0), (12.0, 1.0)),
    )
    offset = -1.3
    baseline = slide_segment(*source, offset)
    assert baseline is not None

    for turns in range(1, 8):
        rotated = slide_segment(
            *[_rotate_segment(segment, turns) for segment in source], offset)
        assert rotated is not None
        expected = [_rotate(point, turns) for point in _points(baseline)]
        actual = _points(rotated)
        assert all(math.dist(a, b) <= 2e-6
                   for a, b in zip(actual, expected))
        assert math.isclose(rotated.after_length, baseline.after_length,
                            abs_tol=2e-6)


def test_interval_is_rotation_invariant_and_stops_before_reversal():
    source = (
        _segment((0.0, 0.0), (3.0, -3.0)),
        _segment((3.0, -3.0), (8.0, -3.0)),
        _segment((8.0, -3.0), (12.0, 1.0)),
    )
    baseline = slide_interval(*source, minimum_length=0.1)
    assert baseline is not None

    for turns in range(1, 8):
        rotated = slide_interval(
            *[_rotate_segment(segment, turns) for segment in source],
            minimum_length=0.1)
        assert rotated is not None
        assert math.isclose(rotated.minimum, baseline.minimum, abs_tol=1e-7)
        assert math.isclose(rotated.maximum, baseline.maximum, abs_tol=1e-7)


def test_slide_geometry_commutes_with_reflection():
    source = (
        _segment((0.0, 0.0), (3.0, -3.0)),
        _segment((3.0, -3.0), (8.0, -3.0)),
        _segment((8.0, -3.0), (12.0, 1.0)),
    )
    offset = -1.3
    baseline = slide_segment(*source, offset)
    reflected = slide_segment(
        *[_reflect_segment(segment) for segment in source], -offset)

    assert baseline is not None
    assert reflected is not None
    expected = [_reflect(point) for point in _points(baseline)]
    assert all(math.dist(a, b) <= 2e-6
               for a, b in zip(_points(reflected), expected))
    assert math.isclose(reflected.after_length, baseline.after_length,
                        abs_tol=2e-6)


def test_interval_reflects_by_reversing_the_signed_offset():
    source = (
        _segment((0.0, 0.0), (3.0, -3.0)),
        _segment((3.0, -3.0), (8.0, -3.0)),
        _segment((8.0, -3.0), (12.0, 1.0)),
    )
    baseline = slide_interval(*source, minimum_length=0.1)
    reflected = slide_interval(
        *[_reflect_segment(segment) for segment in source],
        minimum_length=0.1)

    assert baseline is not None
    assert reflected is not None
    assert math.isclose(reflected.minimum, -baseline.maximum, abs_tol=1e-7)
    assert math.isclose(reflected.maximum, -baseline.minimum, abs_tol=1e-7)


def test_g3_policy_stops_at_first_exact_obstacle_and_keeps_best_slide():
    source = (
        _segment((86.3, 92.5), (92.4, 86.4)),
        _segment((92.4, 86.4), (132.3, 86.4)),
        _segment((132.3, 86.4), (141.2, 95.3)),
    )

    def clears(segments):
        return segments[1].start_y <= 90.2 + 1e-9

    context = types.SimpleNamespace(
        coord=types.SimpleNamespace(grid_step=0.1),
        clearance_adapter=types.SimpleNamespace(connector_clears=clears))
    candidates = list(_reachable_segment_slides(
        context, source, [], [], ((86.3, 92.5), (141.2, 95.3))))

    assert len(candidates) == 1
    middle = candidates[0][1]
    assert math.isclose(middle.start_y, 90.2, abs_tol=1e-9)
    assert math.isclose(middle.end_y, 90.2, abs_tol=1e-9)


def test_length_rate_and_useful_direction_across_rotations_and_reflections():
    source = (_segment((0, 0), (3, -3)),
              _segment((3, -3), (8, -3)),
              _segment((8, -3), (12, 1)))
    expected = 2 - 2 * math.sqrt(2)
    for reflected in (False, True):
        for turns in range(8):
            geometry = [_rotate_segment(s, turns) for s in source]
            if reflected:
                geometry = [_reflect_segment(s) for s in geometry]
            rate = slide_length_rate(*geometry)
            assert math.isclose(rate, -expected if reflected else expected, abs_tol=1e-8)
            observed = []
            def clear(candidate):
                observed.append(calculate_route_length(candidate))
                return True
            context = types.SimpleNamespace(coord=types.SimpleNamespace(grid_step=.1),
                clearance_adapter=types.SimpleNamespace(connector_clears=clear))
            list(_reachable_segment_slides(context, geometry, [], [], ()))
            assert observed
            assert all(length < calculate_route_length(geometry) for length in observed)


def test_neutral_slide_never_calls_clearance():
    source = (_segment((0, 0), (4, 0)), _segment((4, 0), (6, 2)),
              _segment((6, 2), (10, 2)))
    def forbidden(_):
        raise AssertionError('No useful shortening direction')
    context = types.SimpleNamespace(coord=types.SimpleNamespace(grid_step=.1),
        clearance_adapter=types.SimpleNamespace(connector_clears=forbidden))
    assert list(_reachable_segment_slides(context, source, [], [], ())) == []
