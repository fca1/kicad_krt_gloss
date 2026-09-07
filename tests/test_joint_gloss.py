import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss.algorithm import _segments_for_points
from dgloss.context import build_gloss_context
from dgloss.pipeline import _grade, _validate_final
from dgloss.krt_api import calculate_route_length
from tests.test_local_micro_cleanup import make_example
from tools.joint_gloss import shorten_routes, simplify_candidate
from tools import joint_gloss as joint


@pytest.mark.parametrize('points,neutral', [
    ([(0., 0.), (1., 0.), (2., 0.), (3., 0.)], True),
    ([(0., 0.), (1., 1.), (2., 1.), (3., 0.)], False),
])
def test_common_engine_accepts_both_objectives_with_krt(points, neutral):
    example, config, source = make_example(points)
    pcb = example.pcb_data
    context = build_gloss_context(pcb, config, [1])
    grade = _grade(pcb, 1)
    length = calculate_route_length(source)
    _, added, changes, _ = shorten_routes(context, [], net_ids=[1])
    assert added
    assert len(pcb.segments) < len(source)
    gain = length - calculate_route_length(pcb.segments)
    assert abs(gain) < 1e-9 if neutral else gain > .1
    _validate_final(context, {1: grade}, length, changes)


def test_simplification_keeps_backtrack_and_short_leg():
    source = _segments_for_points([(0., 0.), (2., 0.), (1., 0.), (1., .01)], 'F.Cu', .2, 1)
    assert simplify_candidate(source) == source


def test_one_search_combines_neutral_simplification_and_shortcut(monkeypatch):
    points = [(0., 0.), (1., 0.), (2., 0.), (3., 1.), (4., 1.), (5., 0.)]
    example, config, source = make_example(points)
    pcb = example.pcb_data
    context = build_gloss_context(pcb, config, [1])
    grade = _grade(pcb, 1)
    length = calculate_route_length(source)
    def candidates(a, b, layer, width, net):
        if (a, b) in ((points[0], points[2]), (points[2], points[-1])):
            yield _segments_for_points([a, b], layer, width, net)
    monkeypatch.setattr(joint, '_candidate_segments', candidates)
    monkeypatch.setattr(joint, '_adaptive_chamfer_candidates', lambda *a, **k: [])
    monkeypatch.setattr(joint, '_reachable_segment_slides', lambda *a, **k: [])
    _, added, changes, _ = shorten_routes(context, [], net_ids=[1])
    assert len(added) == 2
    assert len(pcb.segments) == 2
    assert all(s not in pcb.segments for s in source)
    _validate_final(context, {1: grade}, length, changes)


@pytest.mark.parametrize('points', [
    [(0., 0.), (1., 1.), (2., 2.)],
    [(0., 0.), (-1., 1.), (-2., 2.)],
    [(0., 0.), (0., -1.), (0., -2.)],
])
def test_collinear_merge_preserves_geometry(points):
    source = _segments_for_points(points, 'F.Cu', .2, 1)
    result = simplify_candidate(source)
    assert len(result) == 1
    assert calculate_route_length(result) == pytest.approx(calculate_route_length(source))
    assert (result[0].start_x, result[0].start_y) == points[0]
    assert (result[0].end_x, result[0].end_y) == points[-1]
