"""Physical broad phases retain KRT decisions, including degenerate inputs."""
import math
import random

import numpy as np
import pytest

from dgloss.krt_api import BoardInfo, GridRouteConfig, Pad, PCBData, Segment, FP_EPS_MM
from dgloss.krt_clearance import KrtClearanceAdapter, _exact_foreign_hole_distance
from dgloss.krt_sweep import foreign_pad_clearance_distance
from dgloss import clearance_preparation, krt_clearance, krt_sweep


def pad(x=0., y=0., net=2, polygons=None, **attributes):
    result = Pad('U1', '1', x, y, 0., 0., .1, .1, 'rect', ['F.Cu'], net, str(net))
    result.polygons = polygons
    for name, value in attributes.items():
        setattr(result, name, value)
    return result


def adapter(pads, net_clearances=None):
    by_net = {}
    for item in pads:
        by_net.setdefault(item.net_id, []).append(item)
    pcb = PCBData(BoardInfo({}, ['F.Cu', 'B.Cu'], None), {}, {}, [], [], by_net)
    config = GridRouteConfig(clearance=.2, layers=['F.Cu'])
    config.net_clearances = net_clearances
    return KrtClearanceAdapter(pcb, config)


def polygon_decision(a, start, end, half_width=.1, effective=.2, net=1):
    args = (net, *start, *end, 'F.Cu', effective)
    exact = foreign_pad_clearance_distance(a.pcb, *args, a.net_clearances, half_width)
    filtered = a._pad_distance(*args, half_width)
    required = effective + half_width - FP_EPS_MM
    assert (filtered >= required) == (exact >= required)
    return filtered >= required


def hole_decision(a, start, end, half_width=.1, net=1):
    args = (a.pcb, net, *start, *end, a.npth_clearance)
    exact = _exact_foreign_hole_distance(*args)
    filtered = _exact_foreign_hole_distance(
        *args, prepared_holes=a._prepared_holes(), half_width=half_width)
    required = a.npth_clearance + half_width - FP_EPS_MM
    assert (filtered >= required) == (exact >= required)
    return filtered >= required


def rectangle(x, y, width=.4, height=.4):
    return [(x, y), (x+width, y), (x+width, y+height), (x, y+height)]


def transform(point, angle, reflection):
    x, y = point
    x *= reflection
    c, s = math.cos(angle), math.sin(angle)
    return (c*x-s*y, s*x+c*y)


@pytest.mark.parametrize('angle', [0., .371, math.pi/2, 2.117])
@pytest.mark.parametrize('reflection', [-1, 1])
@pytest.mark.parametrize('delta', [-2e-9, 0., 2e-9])
def test_polygon_components_offsets_rules_and_threshold(angle, reflection, delta):
    rings = [rectangle(40., 30.), rectangle(3., 2., .4, .8)]
    rings = [[transform(p, angle, reflection) for p in ring] for ring in rings]
    # The copper anchor is unrelated to the real custom-pad components.
    a = adapter([pad(-90., 80., polygons=rings, local_clearance=.6)], {2: .8})
    start = transform((2.1-delta, 2.1), angle, reflection)
    end = transform((2.1-delta, 2.6), angle, reflection)
    assert polygon_decision(a, start, end) == (delta >= 0.)


def test_distant_polygon_is_skipped_and_same_net_unchanged(monkeypatch):
    a = adapter([pad(polygons=[rectangle(500., 500.)]),
                 pad(net=1, polygons=[rectangle(0., 0.)])])
    calls = []
    original = krt_sweep.polygon_axis_distance
    monkeypatch.setattr(krt_sweep, 'polygon_axis_distance',
                        lambda *args: (calls.append(args), original(*args))[1])
    assert a._pad_distance(1, 0., 0., 1., 0., 'F.Cu', .2, .1) == math.inf
    assert calls == []


@pytest.mark.parametrize('rings', [[], [[]],
    [[(math.nan, 100.), (101., 100.), (100., 101.)]],
    [[(1e200, 100.), (101., 100.), (100., 101.)]]])
def test_invalid_polygon_bounds_keep_exact_path(rings, monkeypatch):
    assert clearance_preparation.polygon_bounds(rings) is None
    if not rings:
        return
    a = adapter([pad(polygons=rings)])
    calls = []
    monkeypatch.setattr(krt_sweep, 'polygon_axis_distance',
                        lambda *args: (calls.append(args), 0.)[1])
    assert a._pad_distance(1, 0., 0., 1., 0., 'F.Cu', .2, .1) == 0.
    assert len(calls) == 1


@pytest.mark.parametrize('coordinate', [math.nan, math.inf, 1e200])
def test_invalid_query_keeps_polygon_exact_path(coordinate, monkeypatch):
    a = adapter([pad(polygons=[rectangle(50., 50.)])])
    calls = []
    monkeypatch.setattr(krt_sweep, 'polygon_axis_distance',
                        lambda *args: (calls.append(args), 0.)[1])
    a._pad_distance(1, coordinate, 0., coordinate, 1., 'F.Cu', .2, .1)
    assert len(calls) == 1


@pytest.mark.parametrize('angle', [0., 27., 90., 139.])
@pytest.mark.parametrize('reflection', [-1, 1])
@pytest.mark.parametrize('delta', [-2e-9, 0., 2e-9])
def test_offset_slot_and_ring_uncovered_holes_keep_threshold(angle, reflection, delta):
    # Tiny copper elsewhere must not hide the larger, rotated exposed drill.
    origin = transform((3., 2.), math.radians(angle), reflection)
    hole = pad(90., 80., drill=4., drill_w=4., drill_h=.6,
               hole_x=origin[0], hole_y=origin[1],
               rotation=-angle if reflection == 1 else 180.-angle,
               local_clearance=.8, pad_type='thru_hole')
    a = adapter([hole])
    start = transform((2., 3.2+delta), math.radians(angle), reflection)
    end = transform((4., 3.2+delta), math.radians(angle), reflection)
    assert hole_decision(a, start, end) == (delta >= 0.)


def test_hole_arrays_prepared_once_exact_without_width_and_same_net(monkeypatch):
    a = adapter([pad(50., 50., drill=2., pad_type='np_thru_hole'),
                 pad(0., 0., net=1, drill=4., pad_type='np_thru_hole')])
    original = krt_clearance._foreign_hole_capsules
    calls = []
    monkeypatch.setattr(krt_clearance, '_foreign_hole_capsules',
                        lambda pcb: (calls.append(pcb), original(pcb))[1])
    prepared = a._prepared_holes()
    assert a._prepared_holes() is prepared
    assert len(calls) == 1
    exact = _exact_foreign_hole_distance(a.pcb, 1, 0., 0., 1., 0., .2,
                                         prepared_holes=prepared)
    assert math.isfinite(exact)
    filtered = _exact_foreign_hole_distance(a.pcb, 1, 0., 0., 1., 0., .2,
                                            prepared_holes=prepared, half_width=.1)
    assert filtered == math.inf
    assert len(calls) == 1
    # A new action gets new fixed geometry even if pad counts are unchanged.
    fresh = adapter([pad(0., 0., drill=2., pad_type='np_thru_hole')])
    assert not hole_decision(fresh, (-1., 0.), (1., 0.))


@pytest.mark.parametrize('coordinate', [math.nan, math.inf, 1e200])
def test_invalid_hole_geometry_reaches_exact_primitive(coordinate, monkeypatch):
    a = adapter([pad(coordinate, 50., drill=2., pad_type='np_thru_hole')])
    calls = []
    monkeypatch.setattr(krt_clearance, '_seg_capsule_axis_dist',
                        lambda *args: (calls.append(args), np.zeros(len(args[4])))[1])
    assert _exact_foreign_hole_distance(a.pcb, 1, 0., 0., 1., 0., .2,
        prepared_holes=a._prepared_holes(), half_width=.1) == -1.
    assert len(calls) == 1


def test_random_decisions_match_exact_for_polygons_and_holes():
    rng = random.Random(97532)
    pads = [pad(polygons=[rectangle(rng.uniform(-15, 15), rng.uniform(-15, 15),
                                    rng.uniform(.1, 3), rng.uniform(.1, 3))],
                net=i % 3, local_clearance=rng.uniform(0, 2)) for i in range(24)]
    holes = [pad(rng.uniform(-15, 15), rng.uniform(-15, 15), net=i % 3,
                 drill=3., drill_w=3., drill_h=rng.uniform(.1, 1),
                 rotation=rng.uniform(-180, 180), local_clearance=rng.uniform(0, 2),
                 pad_type='np_thru_hole') for i in range(24)]
    polygon_adapter, hole_adapter = adapter(pads, {2: 1.3}), adapter(holes)
    for _ in range(120):
        start = (rng.uniform(-25, 25), rng.uniform(-25, 25))
        end = (rng.uniform(-25, 25), rng.uniform(-25, 25))
        half_width = rng.uniform(.01, 2)
        polygon_decision(polygon_adapter, start, end, half_width)
        hole_decision(hole_adapter, start, end, half_width)
