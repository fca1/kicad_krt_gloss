import math
import random
from types import SimpleNamespace as NS
import pytest
from kicad_parser import PCBData, BoardInfo, Net, Segment, Via
from routing_config import GridRouteConfig
from dgloss.tests.test_g0_g1_g3 import _pad
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.context import GlossContext
from tools.prototype_gloss_perf import activate, MODES


def make_adapter():
    rng = random.Random(415)
    segments = [Segment(rng.uniform(-8, 8), rng.uniform(-8, 8),
                        rng.uniform(-8, 8), rng.uniform(-8, 8), .15,
                        ['F.Cu', 'B.Cu'][i % 2], 2) for i in range(20)]
    vias = [Via(rng.uniform(-8, 8), rng.uniform(-8, 8), .6, .3,
                ['F.Cu', 'B.Cu'], 1 if i % 2 else 2) for i in range(8)]
    pads = []
    for i, shape in enumerate(['rect', 'roundrect', 'circle', 'oval', 'custom']):
        pad = _pad('X'+str(i), i*3-6, 4, 2, size=.8)
        pad.shape, pad.rect_rotation, pad.roundrect_rratio = shape, i*27, .25
        pad.local_clearance = .3
        if shape == 'custom':
            pad.polygons = [[(6, 4), (6.1, 4.1), (6, 4.3)], [(7, 4), (7.1, 4), (7, 4.2)]]
        pads.append(pad)
    pcb = PCBData(BoardInfo({}, ['F.Cu', 'B.Cu'], (-20, -20, 20, 20)),
                  {1: Net(1, 'A'), 2: Net(2, 'B')}, {}, vias, segments, {1: [], 2: pads})
    cfg = GridRouteConfig(track_width=.15, clearance=.2, grid_step=.1,
                         layers=['F.Cu', 'B.Cu'], board_edge_clearance=0.)
    return KrtClearanceAdapter(pcb, cfg)


@pytest.mark.parametrize('modes', [(mode,) for mode in MODES] + [MODES])
def test_same_exact_clearance_decisions(modes):
    rng = random.Random(65)
    queries = [Segment(rng.uniform(-10, 10), rng.uniform(-10, 10),
                       rng.uniform(-10, 10), rng.uniform(-10, 10), .15, 'F.Cu', 1)
               for _ in range(120)]
    ref = make_adapter()
    expected = [(ref.segment_clears(s), ref.via_clears(Via(s.start_x, s.start_y, .6, .3, ['F.Cu','B.Cu'], 1)),
                 ref.via_sweep_clears(Via(s.start_x, s.start_y, .6, .3, ['F.Cu','B.Cu'], 1),
                                     Via(s.end_x, s.end_y, .6, .3, ['F.Cu','B.Cu'], 1))) for s in queries]
    with activate(modes):
        actual = make_adapter()
        for s, answers in zip(queries, expected):
            old = Via(s.start_x, s.start_y, .6, .3, ['F.Cu','B.Cu'], 1)
            new = Via(s.end_x, s.end_y, .6, .3, ['F.Cu','B.Cu'], 1)
            assert (actual.segment_clears(s), actual.via_clears(old), actual.via_sweep_clears(old,new)) == answers


def test_prepared_pad_distances_are_exact_not_rounded():
    ref = make_adapter()
    with activate(('pads',)):
        actual = make_adapter()
        for angle in range(0, 360, 7):
            x, y = 7*math.cos(math.radians(angle)), 7*math.sin(math.radians(angle))
            args = (1, x, y, x+.137, y+.391, 'F.Cu', .2, .075)
            assert actual._pad_distance(*args) == ref._pad_distance(*args)


def test_reference_retention_excludes_changed_and_all_zone_nets():
    ctx = object.__new__(GlossContext)
    ctx.pcb_data = NS(_gloss_reference_grades={1:'changed',2:'zone',3:'unchanged'}, zones=[NS(net_id=2)])
    ctx.search_cache, ctx.zone_invalidations, ctx.editable_segment_ids = None, 0, None
    with activate(('references',)):
        ctx.replace_editable_segments([NS(net_id=1)], [])
    assert ctx.pcb_data._gloss_reference_grades == {3:'unchanged'}


def test_via_bounds_refresh_after_copper_replacement_and_large_clearance():
    with activate(('vias',)):
        a = make_adapter()
        a.pcb.vias, a.pcb.pads_by_net = [], {}
        a.pcb.segments = [Segment(7, 7, 8, 8, .2, 'F.Cu', 2)]
        via = Via(0, 0, .6, .3, ['F.Cu','B.Cu'], 1)
        assert a.via_clears(via)
        a.pcb.segments = [Segment(-1, 0, 1, 0, .2, 'F.Cu', 2)]
        assert not a.via_clears(via)
    with activate(('vias',)):
        a = make_adapter()
        a.pcb.vias, a.pcb.pads_by_net = [], {}
        a.net_clearances = {2: 7.}
        a.pcb.segments = [Segment(-1, 6, 1, 6, .2, 'F.Cu', 2)]
        assert not a.via_clears(via)


def test_same_net_drill_and_mid_sweep_obstacle_are_retained():
    with activate(('vias',)):
        a = make_adapter()
        a.pcb.segments, a.pcb.pads_by_net = [], {}
        a.pcb.vias = [Via(0,0,.6,.3,['F.Cu','B.Cu'],1)]
        assert not a.via_clears(Via(.1,0,.6,.3,['F.Cu','B.Cu'],1))
        a.pcb.vias = []
        a.pcb.segments = [Segment(0,-.1,1,-.1,.2,'F.Cu',2)]
        assert not a.via_sweep_clears(Via(-5,0,.6,.3,['F.Cu','B.Cu'],1),
                                    Via(5,0,.6,.3,['F.Cu','B.Cu'],1))


@pytest.mark.xfail(strict=True, reason='Existing KRT segment-overlap predicate misses this perpendicular crossing; not changed by performance prototype')
def test_existing_perpendicular_via_sweep_gap():
    a = make_adapter()
    a.pcb.vias, a.pcb.pads_by_net = [], {}
    a.pcb.segments = [Segment(0,-1,0,1,.2,'F.Cu',2)]
    assert not a.via_sweep_clears(Via(-5,0,.6,.3,['F.Cu','B.Cu'],1),
                                Via(5,0,.6,.3,['F.Cu','B.Cu'],1))


def test_prototype_restores_hooks_even_after_exception():
    original = KrtClearanceAdapter._segment_clears
    with pytest.raises(RuntimeError):
        with activate():
            assert KrtClearanceAdapter._segment_clears is not original
            raise RuntimeError('abort experiment')
    assert KrtClearanceAdapter._segment_clears is original
