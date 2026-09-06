"""Small geometry checks for the optional track-corridor prototype."""

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


def _context(obstacles=(), step=0.1):
    def clears(segment):
        return all(point_to_segment_distance(
            x, y, segment.start_x, segment.start_y,
            segment.end_x, segment.end_y) > radius + segment.width / 2
            for x, y, radius in obstacles)
    return SimpleNamespace(
        coord=SimpleNamespace(grid_step=step),
        clearance_adapter=SimpleNamespace(segment_clears=clears))


def test_clear_final_shortcut_cannot_cross_an_obstacle_during_deformation():
    source = [(0, 0), (2, -2), (8, -2), (10, 0)]
    target = [Segment(0, 0, 10, 0, 0.2, "F.Cu", 1)]
    context = _context([(5, -1, 0.3)])
    assert context.clearance_adapter.segment_clears(target[0])
    assert not stays_in_corridor(context, source, target)
    assert stays_in_corridor(_context(), source, target)


def test_motion_between_samples_is_covered_with_coarse_grid():
    # At the single midpoint the track lies at y=.5, well clear of the tiny
    # obstacle at y=.25. The width envelope must catch the intervening motion.
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
