"""Geometry checks for the continuous track-corridor certificate."""

from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "KRT", ROOT / "KRT" / "py_router",
             ROOT / "KRT" / "rust_router"):
    sys.path.insert(0, str(path))

from geometry_utils import point_to_segment_distance
from kicad_parser import Segment
from dgloss.corridor import stays_in_corridor
from dgloss.krt_api import point_in_polygon


def _context(obstacles=(), step=0.1):
    def clears(segment):
        return all(point_to_segment_distance(
            x, y, segment.start_x, segment.start_y,
            segment.end_x, segment.end_y) > radius + segment.width / 2
            for x, y, radius in obstacles)
    def sweep(points, template):
        return (all(clears(Segment(*a, *b, template.width, template.layer, template.net_id))
                    for a, b in zip(points, points[1:] + points[:1])) and
                not any(point_in_polygon(x, y, points) for x, y, _ in obstacles))
    return SimpleNamespace(
        coord=SimpleNamespace(grid_step=step),
        clearance_adapter=SimpleNamespace(segment_clears=clears, sweep_triangle_clears=sweep))


def test_clear_final_shortcut_cannot_cross_an_obstacle_during_deformation():
    source = [(0, 0), (2, -2), (8, -2), (10, 0)]
    target = [Segment(0, 0, 10, 0, 0.2, "F.Cu", 1)]
    context = _context([(5, -1, 0.3)])
    assert context.clearance_adapter.segment_clears(target[0])
    assert not stays_in_corridor(context, source, target)
    assert stays_in_corridor(_context(), source, target)


def test_motion_between_samples_is_covered_with_coarse_grid():
    # A midpoint-only check would miss this obstacle. The filled sweep must
    # catch it regardless of the routing grid, without width inflation.
    source = [(0, 0), (10, 0)]
    target = [Segment(0, 1, 10, 1, 0.02, "F.Cu", 1)]
    assert not stays_in_corridor(_context([(5, .25, .01)], step=2),
                                 source, target)


def test_expired_budget_rejects_an_unchecked_deformation():
    source = [(0, 0), (2, -2), (8, -2), (10, 0)]
    target = [Segment(0, 0, 10, 0, 0.2, "F.Cu", 1)]
    assert not stays_in_corridor(_context(), source, target, deadline=0)


def test_unchanged_polyline_with_different_segmentation_is_allowed():
    target = [Segment(0, 0, 10, 0, 0.2, "F.Cu", 1)]
    assert stays_in_corridor(_context(), [(0, 0), (3, 0), (10, 0)], target)


def test_collinear_fold_near_obstacle_has_no_artificial_lateral_width():
    import math
    for angle in range(0, 360, 45):
        for reflection in (-1, 1):
            c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            def rotate(x, y):
                y *= reflection
                return (c*x-s*y, s*x+c*y)
            source = [rotate(1.41, 0), rotate(0, 0), rotate(13.42, 0)]
            target = [Segment(*source[0], *source[-1], .2, 'F.Cu', 1)]
            obstacle = (*rotate(7, .3), .1524)
            for step in (.01, .1, 2):
                assert stays_in_corridor(_context([obstacle], step), source, target)
