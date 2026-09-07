"""Conservative prototype: certify one continuous track-chain deformation.

Corresponding points use normalized arc length. This is a sufficient test for
this particular deformation, not a search for every possible free deformation.
Intermediate lines need not be octolinear; only emitted copper must be.
"""

import math
from .execution import perf_counter

from dgloss.krt_api import Segment


def _parameterize(points):
    knots = [0.0]
    for a, b in zip(points, points[1:]):
        knots.append(knots[-1] + math.dist(a, b))
    if knots[-1] <= 1e-12:
        return None
    return [value / knots[-1] for value in knots]


def _at(points, knots, value):
    for index in range(1, len(knots)):
        if value <= knots[index] + 1e-12:
            length = knots[index] - knots[index - 1]
            t = (value - knots[index - 1]) / length if length else 0.0
            a, b = points[index - 1:index + 1]
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return points[-1]


def stays_in_corridor(context, source_points, candidate, deadline=None):
    """Check the swept track with KRT's existing clearance adapter.

    Sample the deformation at interval midpoints, inflating track radius by
    the maximum motion to either interval boundary. Thus intermediate motion
    is covered too, rather than allowing a jump between two clear samples.
    Guarantees remain subject to the underlying KRT clearance predicates.
    """
    if not candidate:
        return False
    target_points = [(candidate[0].start_x, candidate[0].start_y)] + [
        (segment.end_x, segment.end_y) for segment in candidate]
    old_knots = _parameterize(source_points)
    new_knots = _parameterize(target_points)
    if old_knots is None or new_knots is None:
        return False
    knots = sorted(set(old_knots + new_knots))
    old = [_at(source_points, old_knots, value) for value in knots]
    new = [_at(target_points, new_knots, value) for value in knots]
    displacement = max(math.dist(a, b) for a, b in zip(old, new))
    if displacement <= 1e-9:
        return True
    steps = max(1, math.ceil(displacement / context.coord.grid_step))
    if steps > 2000:
        return False  # Bound prototype cost; never accept an unchecked sweep.
    template = candidate[0]
    width = template.width + displacement / steps
    for index in range(steps):
        t = (index + 0.5) / steps
        points = [(a[0] + t * (b[0] - a[0]),
                   a[1] + t * (b[1] - a[1])) for a, b in zip(old, new)]
        for a, b in zip(points, points[1:]):
            if deadline is not None and perf_counter() >= deadline:
                return False
            probe = Segment(start_x=a[0], start_y=a[1], end_x=b[0], end_y=b[1],
                            width=width, layer=template.layer,
                            net_id=template.net_id)
            if not context.clearance_adapter.segment_clears(probe):
                return False
    return True
