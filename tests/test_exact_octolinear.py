"""No routing-grid angular tolerance or rounded construction anchors."""
import math
from types import SimpleNamespace
import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss.route_geometry import _candidate_segments, _octolinear_points
from dgloss.algorithm import _candidate_geometry_valid
from dgloss.krt_api import Segment


@pytest.mark.parametrize('angle', range(0, 360, 45))
@pytest.mark.parametrize('reflection', [-1, 1])
def test_off_grid_anchors_are_preserved_without_bend_rounding(angle, reflection):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    def transform(x, y):
        y *= reflection
        return (123.456789 + c*x-s*y, 98.765432 + s*x+c*y)
    a, b = transform(0, 0), transform(2.345678, 1.234567)
    candidates = list(_candidate_segments(a, b, 'F.Cu', .2, 1))
    assert candidates
    for candidate in candidates:
        assert (candidate[0].start_x, candidate[0].start_y) == a
        assert (candidate[-1].end_x, candidate[-1].end_y) == b
        assert all(_octolinear_points((p.start_x, p.start_y), (p.end_x, p.end_y))
                   for p in candidate)
        assert all((left.end_x, left.end_y) == (right.start_x, right.start_y)
                   for left, right in zip(candidate, candidate[1:]))


@pytest.mark.parametrize('step', [.001, .1, 1.])
def test_grid_size_cannot_relax_octolinearity(step):
    ctx = SimpleNamespace(coord=SimpleNamespace(grid_step=step))
    assert not _candidate_geometry_valid(ctx, [Segment(0, 0, 2, 2.00001, .2, 'F.Cu', 1)])
    assert _candidate_geometry_valid(ctx, [Segment(0, 0, 2, 2, .2, 'F.Cu', 1)])
