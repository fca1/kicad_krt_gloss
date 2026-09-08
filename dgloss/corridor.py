"""Certify a continuous, vertex-by-vertex track-chain deformation.

Corresponding points use normalized arc length. This is a sufficient test for
this particular deformation, not a search for every possible free deformation.
Intermediate lines need not be octolinear; only emitted copper must be.
"""

import math
from .execution import perf_counter

def _parameterize(points):
    knots = [0.0]
    for a, b in zip(points, points[1:]):
        knots.append(knots[-1] + math.dist(a, b))
    if knots[-1] <= 1e-12:
        return None
    return [value / knots[-1] for value in knots]


def _at(points, knots, value):
    if len(points) == 1:
        return points[0]
    for index, knot in enumerate(knots):
        if value == knot:
            return points[index]
    for index in range(1, len(knots)):
        if value < knots[index]:
            length = knots[index] - knots[index - 1]
            t = (value - knots[index - 1]) / length if length else 0.0
            a, b = points[index - 1:index + 1]
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return points[-1]


def stays_in_corridor(context, source_points, candidate, deadline=None):
    """Check actual triangular sweeps, with no time sampling or width inflation.

    Move corresponding vertices in path order. Each incident edge sweeps a
    triangle while its other endpoint is fixed. This constructs one continuous
    deformation, not a test of all possible homotopies. KRT owns clearance.
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
    template = candidate[0]
    if any((s.width, s.layer, s.net_id) !=
           (template.width, template.layer, template.net_id) for s in candidate):
        return False  # A homogeneous chain is required by this certificate.
    for index, target in enumerate(new):
        if deadline is not None and perf_counter() >= deadline:
            return False
        start = old[index]
        if start == target:
            continue
        for neighbor in (index - 1, index + 1):
            if 0 <= neighbor < len(old) and not context.clearance_adapter.sweep_triangle_clears(
                    (old[neighbor], start, target), template):
                return False
        old[index] = target
    return deadline is None or perf_counter() < deadline
