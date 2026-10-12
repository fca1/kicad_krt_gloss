"""Delayed raster construction must reflect edits and preserve exact-only runs."""
from dataclasses import replace

from test_gloss_fusion_regressions import example
from dgloss.tests.test_g0_g1_g3 import _parallel_board
from dgloss import GlossConfig
from dgloss.context import build_gloss_context
from dgloss.algorithm import _clears_krt_grid
from dgloss.pipeline import run_final_gloss
from dgloss.krt_api import Segment


def test_first_raster_query_includes_prior_foreign_edits():
    outcomes = []
    for eager in (True, False):
        pcb, config, first, foreign = _parallel_board()
        ctx = build_gloss_context(pcb, config)
        if eager:
            ctx.foreign_obstacles(1)
        moved = replace(foreign, start_y=4., end_y=4.)
        ctx.apply_replacement([foreign], [moved])
        ctx.refresh_net_obstacles(2)
        if not eager:
            assert ctx.working_obstacles is None
        checks = []
        for net in (1, 2, 1):
            obstacles = ctx.foreign_obstacles(net)
            checks.append([_clears_krt_grid(ctx, obstacles,
                [Segment(3., y, 7., y, .2, 'F.Cu', net)])
                for y in (4., 5., 6.)])
        outcomes.append(checks)
    assert outcomes[0] == outcomes[1]
    assert outcomes[1][0] == [False, True, True]
    assert outcomes[1][1] == [True, False, True]


def test_corridor_pipeline_needs_no_raster_even_across_g4(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('exact-only stages must not construct a raster')

    monkeypatch.setattr('dgloss.context.build_base_obstacle_map', forbidden)
    pcb, config = example([(0, 0), (4, 0), (5, -1), (5, 5)], [1.4, 1.4, 1.])
    result = run_final_gloss([], pcb, config, GlossConfig(
        stay_in_corridor=True, g4_max_passes=1), net_ids=[1])
    assert result.stats['g5_valid']
    assert result.stats['saved_mm'] >= 1.4141
