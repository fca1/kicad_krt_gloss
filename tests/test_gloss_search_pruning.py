"""Useful borderline candidates survive; impossible searches do no refinement."""
import math

import pytest

from test_adaptive_segment_slide import fixture
from test_gloss_fusion_regressions import example
from dgloss import algorithm, pad_terminals
from dgloss.context import build_gloss_context
from dgloss.krt_api import Segment, calculate_route_length


@pytest.mark.parametrize('turn', range(8))
@pytest.mark.parametrize('reflection', [False, True])
def test_blocked_slide_below_minimum_gain_is_not_refined(monkeypatch, turn, reflection):
    ctx, source, points = fixture(turn, reflection, obstacle_y=2.35)
    ctx.pcb_data.pads_by_net[2][0].shape = 'circle'
    calls = []
    original = algorithm.slide_segment

    def counted(*args, **kwargs):
        calls.append(args[3])
        return original(*args, **kwargs)

    monkeypatch.setattr(algorithm, 'slide_segment', counted)
    assert not list(algorithm._reachable_segment_slides(
        ctx, source, [], [], (points[0], points[-1])))
    assert len(calls) == 1


@pytest.mark.parametrize('turn', range(8))
def test_small_but_useful_slide_still_refines_with_krt(turn):
    ctx, source, points = fixture(turn, obstacle_y=2.43)
    ctx.pcb_data.pads_by_net[2][0].shape = 'circle'
    result, = algorithm._reachable_segment_slides(
        ctx, source, [], [], (points[0], points[-1]))
    gain = calculate_route_length(source) - calculate_route_length(result)
    assert .1 < gain < .11
    assert ctx.clearance_adapter.connector_clears(result)


@pytest.mark.parametrize('gain', [.05, .1 - 1e-10, .1 + 1e-8])
@pytest.mark.parametrize('turn', range(8))
def test_pad_bound_preserves_borderline_searches(monkeypatch, gain, turn):
    # This dogleg's shortest octolinear connector saves exactly ``gain``.
    offset = gain / (2 - math.sqrt(2))
    angle = turn * math.pi / 4

    def rotated(p):
        x, y = p
        return (x * math.cos(angle) - y * math.sin(angle),
                x * math.sin(angle) + y * math.cos(angle))

    points = [rotated(p) for p in [(0, 0), (offset, 0), (offset, 2)]]
    pcb, config = example(points, [.2, .2])
    ctx = build_gloss_context(pcb, config, [1])
    calls = []
    original = pad_terminals._connector_families

    def counted(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(pad_terminals, '_connector_families', counted)
    result = pad_terminals._best_pad_connector(
        ctx, pcb.pads_by_net[1][0], pcb.segments, points, [], [],
        ctx.foreign_obstacles(1))
    if gain == .05:
        assert not calls and result is None
    else:
        assert calls  # The numerical safety margin retains both borderline cases.
        if gain > .1:
            assert result is not None


def test_graph_preparation_preserves_ties_and_exact_rejection_retries(monkeypatch):
    points = [(0, 0), (2, 0), (2, 2)]

    def edge(i, j, changed, edge_id):
        candidate = [Segment(*points[i], *points[j], .2, 'F.Cu', 1)]
        return (j, candidate, changed, calculate_route_length(candidate), edge_id)

    edges = {0: [edge(0, 1, False, None), edge(0, 2, True, 1),
                 edge(0, 2, True, 2)], 1: [edge(1, 2, False, None)]}
    exclusions = [set(), {1}, {1, 2}]
    expected = [algorithm._shortest_path(edges, points, excluded)
                for excluded in exclusions]
    assert [path[-1][1][4] for path in expected] == [1, 2, None]
    calls = []
    original = algorithm._edge_directions

    def counted(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(algorithm, '_edge_directions', counted)
    prepared = {}
    for excluded, path in zip(exclusions, expected):
        assert algorithm._shortest_path(edges, points, excluded, prepared) == path
    assert len(calls) == 4
