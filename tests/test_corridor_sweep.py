"""Filled sweeps use real KRT obstacles, not only boundary-test mocks."""
import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from kicad_parser import PCBData, BoardInfo, Net, Segment, Via
from routing_config import GridRouteConfig
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.tests.test_g0_g1_g3 import _pad


def adapter(segments=(), vias=(), pads=()):
    pcb = PCBData(BoardInfo({}, ['F.Cu', 'B.Cu'], (-20, -20, 20, 20)),
                  {1: Net(1, 'A'), 2: Net(2, 'obstacle')}, {}, list(vias),
                  list(segments), {1: [], 2: list(pads)})
    config = GridRouteConfig(track_width=.02, clearance=.01, grid_step=.1,
                             layers=['F.Cu', 'B.Cu'], board_edge_clearance=0.)
    return KrtClearanceAdapter(pcb, config)


TRIANGLE = ((0., 0.), (10., 0.), (0., 10.))
TEMPLATE = Segment(0, 0, 10, 0, .02, 'F.Cu', 1)


@pytest.mark.parametrize('kind', ['pad', 'custom', 'track', 'via', 'hole', 'keepout', 'cutout'])
def test_enclosed_obstacle_is_rejected_even_when_boundary_is_clear(kind):
    kwargs = {}
    if kind in ('pad', 'custom', 'hole'):
        pad = _pad('X', 3, 3, 2, size=.1)
        if kind == 'custom':
            # Disconnected real copper far from its nominal pad anchor.
            pad.global_x = pad.global_y = 15
            pad.polygons = [[(3, 3), (3.1, 3), (3, 3.1)]]
        if kind == 'hole':
            pad.layers = []
            pad.pad_type = 'np_thru_hole'
            pad.drill = .2
        kwargs['pads'] = [pad]
    elif kind == 'track':
        kwargs['segments'] = [Segment(3, 3, 3.1, 3, .02, 'F.Cu', 2)]
    elif kind == 'via':
        kwargs['vias'] = [Via(3, 3, .2, .1, ['F.Cu', 'B.Cu'], 2)]
    a = adapter(**kwargs)
    ring = [(3, 3), (3.1, 3), (3, 3.1)]
    if kind == 'keepout':
        a.keepouts = [([ring], (3, 3, 3.1, 3.1), {'F.Cu'})]
    if kind == 'cutout':
        # Boundary is deliberately separated from the enclosed board cutout.
        outer = [(-20, -20), (20, -20), (20, 20), (-20, 20)]
        a.edge_rings = [outer, ring]
        a.edge_outer = [outer]
        a.edge_cutouts = [ring]
    assert all(a.segment_clears(Segment(*x, *y, .02, 'F.Cu', 1))
               for x, y in zip(TRIANGLE, TRIANGLE[1:] + TRIANGLE[:1]))
    assert not a.sweep_triangle_clears(TRIANGLE, TEMPLATE)


def test_other_layer_obstacle_does_not_block_sweep():
    a = adapter(segments=[Segment(3, 3, 3.1, 3, .02, 'B.Cu', 2)])
    assert a.sweep_triangle_clears(TRIANGLE, TEMPLATE)


def test_thin_keepout_between_old_sample_positions_is_detected():
    a = adapter()
    ring = [(.049, -.1), (.051, -.1), (.051, .1), (.049, .1)]
    a.keepouts = [([ring], (.049, -.1, .051, .1), {'F.Cu'})]
    assert not a._keepouts_clear(Segment(0, 0, 10, 0, .001, 'F.Cu', 1))


@pytest.mark.parametrize('shape', ['rect', 'roundrect', 'circle', 'oval', 'custom'])
def test_thin_pad_between_old_axis_samples_is_detected(shape):
    pad = _pad('X', .025, 0., 2, size=.001)
    pad.shape = shape
    pad.roundrect_rratio = .25
    if shape == 'custom':
        pad.polygons = [[(.0245, -.001), (.0255, -.001), (.0255, .001), (.0245, .001)]]
    a = adapter(pads=[pad])
    a.clearance = 0.
    assert not a.segment_clears(Segment(0, 0, 10, 0, .001, 'F.Cu', 1))


@pytest.mark.parametrize('kind', ['pad', 'track', 'via', 'hole'])
def test_clearance_override_is_not_clipped_to_a_fixed_neighbourhood(kind):
    kwargs = {}
    if kind in ('pad', 'hole'):
        pad = _pad('X', 0., 6.05, 2, size=.2)
        pad.local_clearance = 6.
        if kind == 'hole':
            pad.pad_type, pad.layers, pad.drill = 'np_thru_hole', [], .2
        kwargs['pads'] = [pad]
    elif kind == 'track':
        kwargs['segments'] = [Segment(-1, 6.05, 1, 6.05, .2, 'F.Cu', 2)]
    else:
        kwargs['vias'] = [Via(0, 6.05, .2, .1, ['F.Cu', 'B.Cu'], 2)]
    a = adapter(**kwargs)
    a.net_clearances = {2: 6.}
    assert not a.segment_clears(Segment(-1, 0, 1, 0, .02, 'F.Cu', 1))


@pytest.mark.parametrize('shape', ['rect', 'roundrect', 'circle', 'oval'])
def test_analytic_pad_distance_uses_krt_shapes_under_rotation(shape):
    import math
    from dgloss.krt_sweep import pad_axis_distance
    from dgloss.krt_api import point_to_pad_distance
    pad = _pad('X', 0., 0., 2, size=2.)
    pad.shape = shape
    pad.size_y = 1.
    pad.roundrect_rratio = .25
    for angle in (0, 30, 45, 90, 135):
        pad.rect_rotation = angle
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        start = (-3*c-2*s, -3*s+2*c)
        end = (3*c-2*s, 3*s+2*c)
        assert pad_axis_distance(start, end, pad) == pytest.approx(1.5)
        for point in (start, end, (0., 0.)):
            assert pad_axis_distance(point, point, pad) == pytest.approx(
                point_to_pad_distance(*point, pad), abs=1e-9)
