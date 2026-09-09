"""Geometry-only regression for the isolated, non-production experiment."""
import pytest
from tools.prototype_centering_supports import solve_supports, winding


POINTS = [(153.1,83.6), (150.1,86.6), (150.1,96.468318),
          (152.331682,98.7), (159.789798,98.7), (160.7574,97.732398),
          (160.7574,96.387198), (160.270202,95.9), (151.6,95.9),
          (151.029289,95.329289), (151.029289,93.992392),
          (151.950971,93.070711), (158.519289,93.070711), (159.705,91.885)]
CONSTRAINTS = [(7,(152.085,95.695)), (7,(159.705,95.695)), (11,(152.085,93.155))]


@pytest.mark.parametrize('turn', range(4))
@pytest.mark.parametrize('reflection', [-1, 1])
def test_joint_supports_are_symmetric_and_keep_anchors(turn, reflection):
    def transform(p):
        x, y = p[0]*reflection, p[1]
        for _ in range(turn):
            x, y = -y, x
        return x, y
    points = list(map(transform, POINTS))
    constraints = [(i, transform(p)) for i, p in CONSTRAINTS]
    result = solve_supports(points, constraints)
    assert result is not None and len(result) == len(points)
    assert result[0] == points[0] and result[-1] == points[-1]
    for index, axis in constraints:
        a, b = result[index:index+2]
        assert abs((axis[0]-a[0])*(b[1]-a[1])-(axis[1]-a[1])*(b[0]-a[0])) < 1e-7
    for y in (89.345,91.885,94.425,96.965):
        assert winding(points+list(reversed(result)), transform((152.085,y))) == 0


def test_incompatible_doors_rejected_not_averaged():
    assert solve_supports(POINTS, CONSTRAINTS+[(7,(159.705,96.0))]) is None


def test_fixed_terminal_cannot_move():
    assert solve_supports(POINTS, [(0,(153.1,84.6))]) is None


def test_reversed_segment_rejected():
    assert solve_supports(POINTS, [(7,(152.085,99.0))]) is None


def test_parallel_supports_explicitly_unsupported():
    assert solve_supports([(0,0),(1,0),(2,0)], []) is None


def test_no_arbitrary_angle_input():
    assert solve_supports([(0,0),(1,0.3),(2,1)], []) is None


@pytest.mark.parametrize('sweep_clear,expired', [(False,False), (True,True), (True,False)])
def test_candidate_requires_sweep_and_deadline(monkeypatch, sweep_clear, expired):
    from types import SimpleNamespace as NS
    from tools.prototype_centering_supports import build_candidate
    from dgloss.route_geometry import _segments_for_points
    from dgloss import chain_topology, protected_centering
    segments = _segments_for_points(POINTS, 'F.Cu', .2, 7)
    chain = NS(points=POINTS, segments=segments, layer='F.Cu', width=.2)
    monkeypatch.setattr(chain_topology, '_simple_chains', lambda *a: [chain])
    monkeypatch.setattr(protected_centering, 'certify_passages', lambda *a: True)
    context = NS(pcb_data=None, segments_editable=lambda s: True,
                 clearance_adapter=NS(segment_clears=lambda s: True,
                                      sweep_triangle_clears=lambda *a: sweep_clear))
    doors = [NS(segment=segments[i], axis=axis) for i, axis in CONSTRAINTS]
    audit = []
    candidate = build_candidate(context, doors, -1 if expired else None, audit=audit)
    if sweep_clear and not expired:
        assert len(candidate.segments) == 7
        assert candidate.source_segments == tuple(segments[6:13])
    else:
        assert candidate is None and 'rejected' in audit[0]
