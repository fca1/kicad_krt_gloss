"""Differential checks against unchanged KRT models and unindexed predicates."""
import math
import random
from dataclasses import replace

import numpy as np
import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from kicad_parser import BoardInfo, Net, PCBData, Segment, Via, Zone
from dgloss import zone_models as fills
from dgloss.route_geometry import _touches_other_same_net
from dgloss.same_net_index import SameNetSegments
from dgloss.pad_terminals import _new_boundary_right_angle
from dgloss.krt_api import pos_key
from dgloss.tests.test_g0_g1_g3 import _pad


def zone_board(angle=0., offset=0., thickness=.1):
    c, s = math.cos(angle), math.sin(angle)
    def point(x, y):
        return offset + x*c-y*s, offset + x*s+y*c
    def seg(a, b, width=.2, net=2, layer='F.Cu'):
        return Segment(*point(*a), *point(*b), width, layer, net)
    zone = Zone(1, 'GND', 'F.Cu', [point(*p) for p in
                [(-2, -2), (2, -2), (2, 2), (-2, 2)]],
                clearance=.2, min_thickness=thickness)
    tracks = [seg((-3, .3), (3, .3)), seg((3, -3), (3, 3), 1., 3),
              seg((-100, 100), (100, 100)), seg((-1, 0), (1, 0), 1., 1),
              seg((-2, 1), (2, 1), 2., 2, 'B.Cu')]
    # Foreign vias must participate even when their layer list omits F.Cu.
    vias = [Via(*point(.8, -.8), .6, .3, ['B.Cu'], 2),
            Via(*point(100, 100), .6, .3, ['F.Cu'], 2)]
    pad = _pad('X', *point(-1, -.8), 2, size=.5)
    pad.local_clearance = .45
    pcb = PCBData(BoardInfo({}, ['F.Cu', 'B.Cu'],
                  (offset-120, offset-120, offset+120, offset+120)),
                  {1: Net(1, 'GND'), 2: Net(2, 'X'), 3: Net(3, 'HV')},
                  {}, vias, tracks, {2: [pad]}, [zone])
    pcb.board_info.keepouts = [{'polygon': [point(*p) for p in
        [(-1.8, -1.8), (-1.5, -1.8), (-1.5, -1.5), (-1.8, -1.5)]],
        'layers': {'F.Cu'}, 'copper_pour_allowed': False}]
    setattr(pcb, fills.krt._NC_ATTR, {1: .25, 3: 1.3})
    return pcb, zone


def assert_same_model(first, second):
    for name in ('ok', 'x0', 'y0', 'cell', 'nx', 'ny', '_n'):
        assert getattr(first, name) == getattr(second, name)
    np.testing.assert_array_equal(first.labels, second.labels)


@pytest.mark.parametrize('angle', [0., .23, math.pi/4, math.pi/2])
@pytest.mark.parametrize('offset', [-13.137, 1000.])
@pytest.mark.parametrize('thickness', [.04, .1, .24])
def test_filtered_zone_is_cell_identical_to_full_krt(angle, offset, thickness):
    pcb, zone = zone_board(angle, offset, thickness)
    subset = fills._zone_obstacle_subset(pcb, zone)
    assert len(subset.segments) < len(pcb.segments)
    assert subset.pads_by_net is pcb.pads_by_net
    assert subset.board_info is pcb.board_info
    assert subset.vias == pcb.vias[:1]
    reference = fills.krt.ZoneFillModel(pcb, zone)
    fills.prepare_zone_models(pcb, [zone])
    model = fills.krt.get_zone_model(pcb, zone)
    assert_same_model(reference, model)
    assert fills.krt.lookup_zone_model(zone) is model
    assert fills.krt.get_fill_models(pcb, 1)['F.Cu'][0] is model


@pytest.mark.parametrize('side', [-1, 1])
@pytest.mark.parametrize('delta', [-1e-9, 0., 1e-9])
def test_zone_clearance_border_and_large_width_are_retained(side, delta):
    pcb, zone = zone_board()
    # Axis is outside the zone but wide copper + foreign rule reach inside.
    x = side * (2. + 1.3 + 1. - .025 + delta)
    pcb.segments = [Segment(x, -2., x, 2., 2., 'F.Cu', 3)]
    subset = fills._zone_obstacle_subset(pcb, zone)
    assert subset.segments == pcb.segments
    assert_same_model(fills.krt.ZoneFillModel(pcb, zone),
                      fills.krt.ZoneFillModel(subset, zone))


def test_zone_models_follow_foreign_edits_and_reset():
    pcb, zone = zone_board()
    fills.prepare_zone_models(pcb, [zone])
    first = fills.krt.get_zone_model(pcb, zone)
    old = pcb.segments[0]
    new = replace(old, start_y=-.3, end_y=-.3)
    pcb.segments = [new] + pcb.segments[1:]
    assert fills.invalidate_copper_models(pcb, [old, new]) == {1}
    fills.prepare_zone_models(pcb, [zone])
    second = fills.krt.get_zone_model(pcb, zone)
    assert second is not first
    assert_same_model(second, fills.krt.ZoneFillModel(pcb, zone))
    pcb.segments = [old] + pcb.segments[1:]
    fills.reset_copper_models(pcb)
    fills.prepare_zone_models(pcb, [zone])
    assert_same_model(first, fills.krt.get_zone_model(pcb, zone))


def test_large_zone_bypasses_filter_and_failed_filter_uses_full_krt(monkeypatch):
    pcb, zone = zone_board()
    pcb.board_info.board_bounds = (-3, -3, 3, 3)
    assert fills._zone_obstacle_subset(pcb, zone) is pcb
    def fail(*args):
        raise ValueError('unavailable broad phase')
    monkeypatch.setattr(fills, '_zone_obstacle_subset', fail)
    fills.prepare_zone_models(pcb, [zone])
    assert_same_model(fills.krt.get_zone_model(pcb, zone),
                      fills.krt.ZoneFillModel(pcb, zone))


def test_new_model_preserves_krt_secondary_cache_capacity_transition(monkeypatch):
    pcb, zone = zone_board()
    monkeypatch.setattr(fills.krt, '_MODELS_BY_ZONE_ID',
                        {i: object() for i in range(64)})
    fills.prepare_zone_models(pcb, [zone])
    # KRT first publishes entry 65; the Gloss wrapper then clears and republishes.
    assert fills.krt._MODELS_BY_ZONE_ID == {
        id(zone): fills.krt.get_zone_model(pcb, zone)}


@pytest.mark.parametrize('angle', [0., .23, math.pi/4, math.pi/2, math.pi])
@pytest.mark.parametrize('reflection', [-1, 1])
def test_indexed_same_net_matches_full_scan(angle, reflection):
    rng = random.Random(783)
    c, s = math.cos(angle), math.sin(angle)
    def point(x, y):
        y *= reflection
        return -2. + x*c-y*s, 4. + x*s+y*c
    def seg(x, y, xx, yy, layer='F.Cu'):
        return Segment(*point(x, y), *point(xx, yy), .2, layer, 1)
    outside = []
    for i in range(90):
        x, y = rng.uniform(-20, 20), rng.uniform(-20, 20)
        outside.append(seg(x, y, x+rng.uniform(-4, 4), y+rng.uniform(-4, 4),
                           'B.Cu' if i%3 == 0 else 'F.Cu'))
    outside += [seg(0, 0, 2, 0), seg(2, 0, 2, 2),
                seg(2, -2e-8, 3, -2e-8), seg(-1e4, -1e4, 1e4, 1e4)]
    index = SameNetSegments(outside)
    vias = [Via(*point(1, 1), .6, .3, ['F.Cu', 'B.Cu'], 1)]
    queries = [seg(0, 0, 3, 0), seg(2, -1e-8, 2, 1),
               seg(1, 1, 1, 1), seg(-1e5, 0, 1e5, 0)]
    for _ in range(60):
        x, y = rng.uniform(-20, 20), rng.uniform(-20, 20)
        queries.append(seg(x, y, x+rng.uniform(-4, 4), y+rng.uniform(-4, 4)))
    for new in queries:
        for allowed in [[], [point(0, 0), point(2, 0)], [point(1, 1)]]:
            assert _touches_other_same_net([new], index, vias, allowed) == \
                   _touches_other_same_net([new], outside, vias, allowed)


def test_cell_border_near_collinear_overlap_and_snapshot_lifetime():
    remote = [Segment(100+i, 100, 101+i, 100, .2, 'F.Cu', 1) for i in range(20)]
    old = Segment(0, -5e-8, 1, -5e-8, .2, 'F.Cu', 1)
    outside = remote + [old]
    snapshot = SameNetSegments(outside)
    new = Segment(.2, 0, .8, 0, .2, 'F.Cu', 1)
    assert _touches_other_same_net([new], snapshot, [], [])
    assert tuple(snapshot.near(new)) == (old,)
    outside[-1] = replace(old, start_y=10, end_y=10)
    assert not _touches_other_same_net([new], SameNetSegments(outside), [], [])
    assert _touches_other_same_net([new], snapshot, [], [])


def test_index_preserves_order_and_retains_long_overflow_segments():
    tracks = [Segment(-1e5, -1e5, 1e5, 1e5, .2, 'F.Cu', 1)]
    tracks += [Segment(i, 0, i+1, 0, .2, 'F.Cu', 1) for i in range(40)]
    index = SameNetSegments(tracks)
    neighbours = list(index.near(Segment(0, -1, 0, 1, .2, 'F.Cu', 1)))
    assert neighbours[0] is tracks[0]
    assert [tracks.index(s) for s in neighbours] == sorted(tracks.index(s) for s in neighbours)


def test_wide_query_and_long_segment_set_still_cull_distant_axes():
    remote = [Segment(1000+i, 1000, 1100+i, 1100, .2, 'F.Cu', 1) for i in range(20)]
    crossing = Segment(0, -1, 0, 1, .2, 'F.Cu', 1)
    index = SameNetSegments(remote + [crossing])
    for new in [Segment(-100, -100, 100, 100, .2, 'F.Cu', 1),
                Segment(-1, 0, 1, 0, .2, 'F.Cu', 1)]:
        assert tuple(index.near(new)) == (crossing,)
        assert _touches_other_same_net([new], index, [], [])


@pytest.mark.parametrize('offset', [-.000000001, 0., .000000001])
@pytest.mark.parametrize('reverse', [False, True])
def test_endpoint_index_preserves_krt_keys_and_boundary_angles(offset, reverse):
    outside = [Segment(0, offset, 0, 2, .2, 'F.Cu', 1),
               Segment(0, 0, 2, 0, .2, 'B.Cu', 1),
               Segment(0, 0, 0, 0, .2, 'F.Cu', 1)]
    if reverse:
        outside = [replace(s, start_x=s.end_x, start_y=s.end_y,
                            end_x=s.start_x, end_y=s.start_y) for s in outside]
    index = SameNetSegments(outside)
    assert tuple(index.at_endpoint('F.Cu', pos_key(0, 0))) == (outside[0], outside[2])
    for xy in [(0, 0), (0, offset), (0, 2), (10, 10)]:
        for x, y in [(1, 0), (1, 1), (0, 1)]:
            candidate = [Segment(x, y, *xy, .2, 'F.Cu', 1)]
            assert _new_boundary_right_angle(candidate, xy, outside) == \
                   _new_boundary_right_angle(candidate, xy, index)
