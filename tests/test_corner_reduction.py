"""Corner search: physical contacts, symmetry and no obstacle jumping."""
import math
from types import SimpleNamespace

import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss.corner_reduction import corner_family, reduce_corner
from dgloss.krt_api import Segment, calculate_route_length
from dgloss.route_geometry import _segments_for_points, _octolinear_points
from test_corridor_sweep import adapter
from dgloss.tests.test_g0_g1_g3 import _pad


SOURCE = [(6., -6.), (0., 0.), (12., 0.)]


def run(points=SOURCE, obstacle=(5., -1.), step=.1):
    pads = [] if obstacle is None else [_pad('BLOCK', *obstacle, 2, size=1.6)]
    for pad in pads:
        pad.shape = 'circle'
    ctx = SimpleNamespace(coord=SimpleNamespace(grid_step=step),
                          clearance_adapter=adapter(pads=pads))
    template = Segment(*points[0], *points[1], .2, 'F.Cu', 1)
    return reduce_corner(ctx, points, template), ctx


def test_shorter_connector_can_have_more_segments_without_an_acute_joint():
    result, ctx = run()
    assert result and len(result) == 4
    assert calculate_route_length(result) < calculate_route_length(
        _segments_for_points(SOURCE, 'F.Cu', .2, 1))-1
    assert ctx.clearance_adapter.connector_clears(result)
    directions = [(s.end_x-s.start_x, s.end_y-s.start_y) for s in result]
    for u, v in zip(directions, directions[1:]):
        assert (u[0]*v[0]+u[1]*v[1])/math.hypot(*u)/math.hypot(*v) == pytest.approx(math.sqrt(.5))


@pytest.mark.parametrize('turns', range(8))
@pytest.mark.parametrize('reflection', [-1, 1])
def test_physical_contact_commutes_with_rotation_and_reflection(turns, reflection):
    angle = turns*math.pi/4
    def transform(p):
        x, y = p[0], reflection*p[1]
        return (x*math.cos(angle)-y*math.sin(angle),
                x*math.sin(angle)+y*math.cos(angle))
    reference, _ = run()
    result, _ = run([transform(p) for p in SOURCE], transform((5., -1.)))
    assert result and len(result) == len(reference)
    for expected, actual in zip(reference, result):
        assert math.dist(transform((expected.start_x, expected.start_y)),
                         (actual.start_x, actual.start_y)) < 2e-6
        assert math.dist(transform((expected.end_x, expected.end_y)),
                         (actual.end_x, actual.end_y)) < 2e-6
        assert _octolinear_points((actual.start_x, actual.start_y),
                                  (actual.end_x, actual.end_y))


def test_contact_is_not_set_by_grid_step():
    first, _ = run(step=.01)
    second, _ = run(step=.1)
    assert calculate_route_length(first) == pytest.approx(
        calculate_route_length(second), abs=2e-6)


def test_an_obstacle_in_the_cap_cannot_be_jumped_to_a_free_destination():
    result, ctx = run()
    free_result, _ = run(obstacle=None)
    assert ctx.clearance_adapter.connector_clears(free_result)
    assert calculate_route_length(result) > calculate_route_length(free_result)+1
    # Advancing the contact by a physical amount must cross the obstacle.
    units, _ = corner_family(SOURCE)
    radius = result[0].end_x
    cap = [(x*(radius+.01), y*(radius+.01)) for x, y in units]
    assert not all(ctx.clearance_adapter.sweep_triangle_clears(
        (SOURCE[1], a, b), result[0]) for a, b in zip(cap, cap[1:]))


def test_blocked_minimum_connector_and_expired_deadline_produce_nothing():
    result, ctx = run(obstacle=(.1, -.1))
    assert result is None
    assert reduce_corner(ctx, SOURCE, Segment(*SOURCE[0], *SOURCE[1], .2, 'F.Cu', 1),
                         deadline=0) is None


@pytest.mark.parametrize('points', [
    [(0, 0), (1, 0), (2, 0)], [(0, 0), (1, 0), (0, 0)],
    [(0, 0), (1, 0), (2, 1)], [(0, 0), (1, .2), (2, 0)],
])
def test_no_artificial_corner_on_straight_gentle_or_non_octolinear_input(points):
    assert corner_family(points) is None


def test_right_angle_absorbs_an_endpoint_without_a_microsegment():
    result, _ = run(points=[(-3., 0.), (0., 0.), (0., 4.)], obstacle=None)
    assert result and all(calculate_route_length([s]) >= .1 for s in result)
    assert calculate_route_length(result) < 7.


def test_same_net_is_an_obstacle_during_the_whole_corner_motion():
    free, ctx = run(obstacle=None)
    obstacle = Segment(3, -.9, 3, -.7, .2, 'F.Cu', 1)
    template = Segment(*SOURCE[0], *SOURCE[1], .2, 'F.Cu', 1)
    result = reduce_corner(ctx, SOURCE, template, outside=[obstacle])
    assert result
    assert calculate_route_length(result) > calculate_route_length(free)+1.


def test_immutable_input_and_tiny_corner_are_preserved():
    points = [(0., 0.), (.05, 0.), (.05, .05)]
    original = list(points)
    result, _ = run(points, obstacle=None)
    assert result is None and points == original


def test_a_rejected_electrical_replacement_does_not_escape_the_guard(monkeypatch):
    from test_local_micro_cleanup import make_example
    from dgloss.local_gloss import local_replacement
    from dgloss.chain_topology import _Chain
    import dgloss.local_gloss as local
    ctx, _, segments = make_example(SOURCE)
    monkeypatch.setattr(local, 'ReplacementGuard', lambda *a: lambda *b: False)
    assert local_replacement(ctx, _Chain(segments, SOURCE, 'F.Cu', .2),
                             1, segments, []) is None
    assert ctx.pcb_data.segments == segments


def test_corridor_revisits_via_changed_nets_before_g5_without_g4(monkeypatch):
    from test_progressive_via import example
    from dgloss import pipeline, GlossConfig
    pcb, cfg = example(pad_stop=True)
    original = pipeline.shorten_routes
    calls = []
    def spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(pipeline, 'shorten_routes', spy)
    result = pipeline.run_final_gloss([], pcb, cfg, GlossConfig(
        stay_in_corridor=True, enable_multipasses=False,
        repeat_until_stable=False), net_ids=[1])
    assert result.stats.get('g5_valid')
    assert result.stats['vias_moved'] > 0
    assert result.stats['g4_passes_completed'] == 0
    local = [call for call in calls if call.get('stage') == 'G3 local']
    assert len(local) == 1
    assert local[0]['net_ids'] == [1] and local[0]['stay_in_corridor']


def test_unchanged_downstream_stages_do_not_repeat_corridor_search(monkeypatch):
    from test_local_micro_cleanup import make_example
    from dgloss import pipeline, GlossConfig
    ctx, cfg, _ = make_example([(1., 1.), (3., 1.), (3., 2.99)], blocked=True)
    original = pipeline.shorten_routes
    calls = []
    def spy(*args, **kwargs):
        calls.append(kwargs.get('stage'))
        return original(*args, **kwargs)
    monkeypatch.setattr(pipeline, 'shorten_routes', spy)
    result = pipeline.run_final_gloss([], ctx.pcb_data, cfg, GlossConfig(
        stay_in_corridor=True, enable_multipasses=False, move_vias=False,
        optimize_pad_approaches=False, move_junctions=False), net_ids=[1])
    assert result.stats.get('g5_valid')
    assert 'G3 local' not in calls
