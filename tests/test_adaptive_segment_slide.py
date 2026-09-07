"""Small orientation, obstacle and budget checks for the opt-in prototype."""
from contextlib import nullcontext
import math
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss.krt_api import Segment
from kicad_parser import PCBData, BoardInfo, Net
from routing_config import GridRouteConfig
from dgloss.tests.test_g0_g1_g3 import _pad
from dgloss.algorithm import _Chain
from dgloss.context import build_gloss_context
from dgloss.segment_sliding import slide_segment
from dgloss.local_gloss import local_replacement
from dgloss.topology import ReplacementGuard
from tools.adaptive_segment_slide import best_slide, SearchStats
from tools.adaptive_slide_local import local_replacement as adaptive_local


def fixture(turns=0, reflect=False, width=.2, obstacle_y=3.5, clearance=.1):
    def transform(p):
        x, y = p
        if reflect:
            x = -x
        angle = turns * math.pi / 4
        return (x*math.cos(angle)-y*math.sin(angle),
                x*math.sin(angle)+y*math.cos(angle))
    points = [transform(p) for p in [(0,5),(3,2),(8,2),(12,6)]]
    source = [Segment(*a,*b,width,'F.Cu',1) for a,b in zip(points,points[1:])]
    pads = {1: [_pad('A',*points[0],1), _pad('B',*points[-1],1)],
            2: [_pad('X',*transform((5,obstacle_y)),2,size=width)]}
    pcb = PCBData(BoardInfo({},['F.Cu','B.Cu'],(-30,-30,30,30)),
                  {1:Net(1,'N'),2:Net(2,'X')},{},[],source,pads)
    context = build_gloss_context(pcb,GridRouteConfig(
        grid_step=.1,track_width=width,clearance=clearance,
        layers=['F.Cu','B.Cu'],board_edge_clearance=0),net_ids=[1])
    return context, source, points


@pytest.mark.parametrize('turns', range(8))
@pytest.mark.parametrize('reflect', [False, True])
def test_partial_slide_in_every_direction(turns, reflect):
    ctx, source, points = fixture(turns, reflect)
    stats = SearchStats()
    guard = ReplacementGuard(ctx.pcb_data,1,source,[])
    result = best_slide(ctx,source,[],[],(points[0],points[-1]),
                        stats=stats,accept_replacement=guard)
    assert result is not None
    assert ctx.clearance_adapter.connector_clears(result)
    assert guard(source,result)
    assert stats.candidates < 20
    assert all(offset < 0 if reflect else offset > 0 for offset in stats.offsets)
    # The middle segment must stop before the swept obstacle, not beyond it.
    distance = math.dist((result[1].start_x,result[1].start_y), points[1]) / math.sqrt(2)
    assert .8 < distance < 1.4


def test_local_search_recovers_the_partial_slide_missed_by_extremes():
    ctx, source, points = fixture()
    chain = _Chain(source,points,'F.Cu',.2)
    assert local_replacement(ctx,chain,1,source,[]) is None
    result = adaptive_local(ctx,chain,1,source,[],stats=SearchStats())
    assert result is not None


def test_thin_obstacle_between_two_clear_grid_positions_cannot_be_jumped():
    ctx, source, points = fixture(width=.01,obstacle_y=2.05,clearance=.005)
    endpoint = list(slide_segment(*source,.1).segments)
    assert ctx.clearance_adapter.connector_clears(source)
    assert ctx.clearance_adapter.connector_clears(endpoint)
    result = best_slide(ctx,source,[],[],(points[0],points[-1]))
    assert result is None or result[1].start_y < 2.05


def test_neutral_slide_uses_no_krt_probes():
    points = [(0,0),(4,0),(6,2),(10,2)]
    source = [Segment(*a,*b,.2,'F.Cu',1) for a,b in zip(points,points[1:])]
    exact = Mock(side_effect=AssertionError('neutral slide must not be tested'))
    ctx = NS(coord=NS(grid_step=.1),clearance_adapter=NS(segment_clears=exact))
    assert best_slide(ctx,source,[],[],(points[0],points[-1])) is None
    exact.assert_not_called()


def test_probe_budget_keeps_the_first_fully_certified_candidate():
    ctx, source, points = fixture()
    ctx.clearance_adapter = NS(segment_clears=lambda s: True,stable_copper=nullcontext)
    stats = SearchStats()
    result = best_slide(ctx,source,[],[],(points[0],points[-1]),stats=stats,max_probes=6)
    assert result is not None
    assert result[1].start_y == pytest.approx(2.1)
    assert stats.segment_probes == 6
    assert stats.capped == 1


def test_expired_deadline_performs_no_checks():
    ctx, source, points = fixture()
    stats = SearchStats()
    assert best_slide(ctx,source,[],[],(points[0],points[-1]),deadline=0,stats=stats) is None
    assert stats.segment_probes == 0


def test_deadline_keeps_a_fully_certified_incumbent(monkeypatch):
    import tools.adaptive_segment_slide as module
    ctx, source, points = fixture()
    now, calls = [0.], [0]
    def clear(segment):
        calls[0] += 1
        if calls[0] == 6:
            now[0] = 2.
        return True
    monkeypatch.setattr(module,'perf_counter',lambda: now[0])
    ctx.clearance_adapter = NS(segment_clears=clear,stable_copper=nullcontext)
    result = best_slide(ctx,source,[],[],(points[0],points[-1]),deadline=1.)
    assert result is not None
    assert result[1].start_y == pytest.approx(2.1)
    assert calls[0] == 6
