"""Small KRT-backed cases extracted from the complete1/Fusion comparison."""
import math
from dataclasses import replace

import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()

from dgloss.krt_api import Segment, calculate_route_length
from dgloss.context import build_gloss_context
from dgloss.width_transitions import transition_replacement
from dgloss.pad_terminals import _walk_terminal_chain
from dgloss.pipeline import run_final_gloss
from dgloss import GlossConfig
from dgloss.tests.test_g0_g1_g3 import _pad
from kicad_parser import PCBData, BoardInfo, Net, Via
from routing_config import GridRouteConfig


def example(points, widths, pad_size=.4):
    segments = [Segment(*a, *b, width, 'F.Cu', 1)
                for a, b, width in zip(points, points[1:], widths)]
    pads = {1: [_pad('A', *points[0], 1, size=pad_size),
                _pad('B', *points[-1], 1, size=pad_size)]}
    pcb = PCBData(BoardInfo({}, ['F.Cu'], (-40., -40., 40., 40.)),
                  {1: Net(1, 'N'), 2: Net(2, 'X')}, {}, [], segments, pads)
    config = GridRouteConfig(track_width=.2, clearance=.1, grid_step=.1,
                             layers=['F.Cu'], board_edge_clearance=0.)
    return pcb, config


@pytest.mark.parametrize('turn', range(8))
@pytest.mark.parametrize('reflection', [-1, 1])
def test_free_width_transition_commutes_with_rotation_and_reflection(turn, reflection):
    def transform(p):
        x, y = p[0], p[1]*reflection
        co, si = math.cos(turn*math.pi/4), math.sin(turn*math.pi/4)
        return (x*co-y*si, x*si+y*co)
    points = [transform(p) for p in [(0, 0), (4, 0), (5, -1), (5, 5)]]
    pcb, config = example(points, [1.4, 1.4, 1.])
    # Storage direction and order must not select a privileged orientation.
    pcb.segments = [replace(s, start_x=s.end_x, start_y=s.end_y,
                            end_x=s.start_x, end_y=s.start_y)
                    for s in reversed(pcb.segments)]
    ctx = build_gloss_context(pcb, config, [1])
    original = list(pcb.segments)
    removed, added = transition_replacement(ctx, 1, original, [])
    assert calculate_route_length(removed)-calculate_route_length(added) == pytest.approx(math.sqrt(2))
    assert sorted(s.width for s in added) == [1., 1.4]
    assert any(math.dist((s.start_x, s.start_y), transform((5, 0))) < 1e-6 or
               math.dist((s.end_x, s.end_y), transform((5, 0))) < 1e-6 for s in added)
    assert pcb.segments == original  # Search alone never mutates.
    outcome = run_final_gloss([], pcb, config, GlossConfig(
        stay_in_corridor=True, enable_multipasses=False), net_ids=[1])
    assert outcome.stats['g5_valid']
    assert outcome.stats['saved_mm'] >= 1.4141


@pytest.mark.parametrize('protection', ['scope', 'locked', 'pad', 'via', 'branch', 'obstacle', 'same_net_sweep', 'expired', 'electrical'])
def test_transition_preserves_protected_or_invalid_copper(protection, monkeypatch):
    pcb, config = example([(0, 0), (4, 0), (5, -1), (5, 5)], [1.4, 1.4, 1.])
    if protection == 'locked':
        pcb.segments[1].locked = True
    if protection == 'pad':
        pcb.pads_by_net[1].append(_pad('FIXED', 5, -1, 1, size=.3))
    if protection == 'branch':
        pcb.segments.append(Segment(5, -1, 8, -1, .2, 'F.Cu', 1))
    if protection == 'via':
        pcb.vias.append(Via(5, -1, .6, .3, ['F.Cu', 'B.Cu'], 1))
    if protection == 'same_net_sweep':
        pcb.segments.append(Segment(4.6, -.2, 4.7, -.2, .01, 'F.Cu', 1))
    if protection == 'obstacle':
        pcb.pads_by_net[2] = [_pad('BLOCK', 4.8, .5, 2, size=.2)]
    ctx = build_gloss_context(pcb, config, [1])
    if protection == 'scope':
        ctx.editable_segment_ids = {id(pcb.segments[0]), id(pcb.segments[1])}
    if protection == 'electrical':
        monkeypatch.setattr('dgloss.width_transitions.ReplacementGuard', lambda *a: lambda *b: False)
    original = list(pcb.segments)
    assert transition_replacement(ctx, 1, original, pcb.vias,
                                  deadline=0 if protection == 'expired' else None) is None
    assert pcb.segments == original


def test_pad_with_internal_joint_is_one_terminal_and_can_shorten_a_prefix():
    points = [(0, 0), (.661056, 0), (4.42, -3.758944), (4.42, -15.44), (8.41, -19.43)]
    pcb, config = example(points, [.1524]*4, pad_size=1.4)
    pcb.pads_by_net[2] = [_pad('X', 0, -5, 2, size=1),
                          _pad('Y', 6, -6, 2, size=1)]
    chain, actual = _walk_terminal_chain(pcb, 1, pcb.pads_by_net[1][0])
    assert len(chain) == 4 and actual == points
    original = calculate_route_length(pcb.segments)
    outcome = run_final_gloss([], pcb, config, GlossConfig(
        stay_in_corridor=True, enable_multipasses=False), net_ids=[1])
    assert outcome.stats['g5_valid']
    assert original-calculate_route_length(pcb.segments) >= .3872


@pytest.mark.parametrize('kind', ['separate_entry', 'branch', 'locked'])
def test_multiple_real_pad_entries_remain_protected(kind):
    pcb, _ = example([(0, 0), (.6, 0), (3, -2.4), (3, -6)], [.2]*3, pad_size=1.4)
    if kind == 'separate_entry':
        pcb.segments.append(Segment(0, .2, -3, .2, .2, 'F.Cu', 1))
    elif kind == 'branch':
        pcb.segments.append(Segment(.6, 0, .6, 3, .2, 'F.Cu', 1))
    else:
        pcb.segments[1].locked = True
    assert _walk_terminal_chain(pcb, 1, pcb.pads_by_net[1][0]) is None


@pytest.mark.parametrize('turn', range(8))
@pytest.mark.parametrize('reflection', [False, True])
def test_slide_refines_the_last_grid_interval_with_real_krt(turn, reflection):
    from test_adaptive_segment_slide import fixture
    from dgloss.algorithm import _reachable_segment_slides
    from dgloss.segment_sliding import slide_segment
    ctx, source, points = fixture(turn, reflection, obstacle_y=3.537)
    # A circular obstacle rotates with the scene. The shared fixture's square
    # stays board-aligned and would change the contact distance at 45 degrees.
    ctx.pcb_data.pads_by_net[2][0].shape = 'circle'
    result, = _reachable_segment_slides(ctx, source, [], [], (points[0], points[-1]))
    coarse = list(slide_segment(*source, -1.2 if reflection else 1.2).segments)
    assert calculate_route_length(result) < calculate_route_length(coarse)-.03
    assert ctx.clearance_adapter.connector_clears(result)
    assert min(calculate_route_length([s]) for s in result) >= .1-1e-8
    assert not list(_reachable_segment_slides(ctx, source, [], [], (), deadline=0))


def test_refined_contact_survives_nanometre_serialization():
    from test_adaptive_segment_slide import fixture
    from dgloss.algorithm import _reachable_segment_slides
    ctx, source, points = fixture(obstacle_y=3.5370006)
    ctx.pcb_data.pads_by_net[2][0].shape = 'circle'
    result, = _reachable_segment_slides(ctx, source, [], [], (points[0], points[-1]))
    written = [replace(s, start_x=round(s.start_x, 6), start_y=round(s.start_y, 6),
                       end_x=round(s.end_x, 6), end_y=round(s.end_y, 6)) for s in result]
    assert ctx.clearance_adapter.connector_clears(written)
