"""Small real-KRT regressions; no board-file or extended stress tests."""
import math
from types import SimpleNamespace
import pytest

from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()

from dgloss.algorithm import _Chain, _segments_for_points
from dgloss.changes import GlossChanges
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.local_gloss import local_replacement
from dgloss.pipeline import _grade, _validate_final
from dgloss.tests.test_g0_g1_g3 import _pad
from kicad_parser import BoardInfo, Net, PCBData
from routing_config import GridRouteConfig
from net_queries import calculate_route_length


def make_example(points, blocked=False):
    segments = _segments_for_points(points, 'F.Cu', .2, 1)
    pads = {1: [_pad('A', *points[0], 1), _pad('B', *points[-1], 1)]}
    if blocked:
        pads[2] = [_pad('X', 2., 2., 2, size=.8)]
    pcb = PCBData(BoardInfo({}, ['F.Cu'], (-20., -20., 20., 20.)),
                  {1: Net(1, 'N1'), 2: Net(2, 'N2')}, {}, [], segments, pads)
    config = GridRouteConfig(track_width=.2, clearance=.1, grid_step=.1,
                             layers=['F.Cu'], board_edge_clearance=0.)
    context = SimpleNamespace(pcb_data=pcb, coord=SimpleNamespace(grid_step=.1),
                              clearance_adapter=KrtClearanceAdapter(pcb, config))
    return context, config, segments


def run_example(points, blocked=False):
    context, config, segments = make_example(points, blocked)
    pcb = context.pcb_data
    before = _grade(pcb, 1)
    result = local_replacement(context, _Chain(segments, points, 'F.Cu', .2),
                               1, segments, [])
    if result:
        removed, added = result
        removed_ids = {id(s) for s in removed}
        pcb.segments = [s for s in segments if id(s) not in removed_ids] + added
        _validate_final(context, {1: before}, calculate_route_length(segments),
                        GlossChanges(segments=[{'new': s} for s in added]))
        assert context.clearance_adapter.connector_clears(added)
    return result, pcb.segments


def test_nearly_diagonal_shortcut_is_repaired_and_final_validation_passes():
    result, final = run_example([(1., 1.), (3., 1.), (3., 2.99)])
    assert result is not None
    assert min(calculate_route_length([s]) for s in final) >= .1 - 1e-9
    assert calculate_route_length(final) < 3.99


def test_existing_micro_segment_is_absorbed_with_its_neighbours():
    result, final = run_example([(1., 1.), (2., 1.), (2.01, 1.01), (2.01, 3.)])
    assert result is not None
    assert min(calculate_route_length([s]) for s in final) >= .1 - 1e-9
    assert len(final) < 3


def test_obstacle_rejects_repaired_candidate_without_removing_input():
    result, final = run_example([(1., 1.), (3., 1.), (3., 2.99)], blocked=True)
    assert result is None
    assert len(final) == 2


def test_small_example_rotations_keep_valid_micro_free_results():
    for turns in (1, 2, 3):
        angle = turns * math.pi / 4
        c, s = math.cos(angle), math.sin(angle)
        points = [(x*c-y*s, x*s+y*c) for x, y in [(1., 1.), (3., 1.), (3., 2.99)]]
        result, final = run_example(points)
        assert result is not None
        assert min(calculate_route_length([seg]) for seg in final) >= .1 - 1e-9


@pytest.mark.parametrize('corridor', [False, True])
def test_pipeline_runs_local_repair_with_final_krt_certificate(monkeypatch, corridor):
    from dgloss import algorithm, GlossConfig
    from dgloss.pipeline import run_final_gloss
    points = [(1., 1.), (3., 1.), (3., 2.99)]
    context, config, original = make_example(points)
    # Isolate the local stage's pipeline wiring from the competing DAG search.
    monkeypatch.setattr(algorithm, '_best_chain_replacement', lambda *a, **k: None)
    result = run_final_gloss([], context.pcb_data, config, GlossConfig(
        stay_in_corridor=corridor, move_vias=False, move_junctions=False,
        optimize_pad_approaches=False, repeat_until_stable=False,
        enable_g3_4=False, budget_seconds=2.), net_ids=[1])
    assert result.stats.get('g5_valid') is True
    assert result.stats['saved_mm'] > .1
    assert min(calculate_route_length([s]) for s in context.pcb_data.segments) >= .1 - 1e-9


def test_local_delta_excludes_unchanged_segments(monkeypatch):
    from dgloss import algorithm, local_gloss
    points = [(1., 1.), (3., 1.), (3., 3.), (5., 3.)]
    context, config, original = make_example(points)
    generate = algorithm._candidate_segments
    monkeypatch.setattr(local_gloss, 'slide_interval', lambda *a, **k: None)
    from dgloss import route_geometry
    monkeypatch.setattr(route_geometry, '_candidate_segments',
                        lambda a, b, *rest: generate(a, b, *rest)
                        if a == points[1] and b == points[3] else [])
    removed, added = local_replacement(
        context, _Chain(original, points, 'F.Cu', .2), 1, original, [])
    assert len(removed) == 2
    assert len(added) == 1
    assert all(s is not original[0] for s in removed + added)
