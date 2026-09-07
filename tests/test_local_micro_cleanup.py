"""Small real-KRT regressions; no board-file or extended stress tests."""
import math
from types import SimpleNamespace

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


def run_example(points, blocked=False):
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
