"""Bounded repairs of short octolinear connectors, with fixed endpoints."""
import math

from kicad_parser import Segment
from net_queries import calculate_route_length


def micro_free_candidates(candidate, minimum_length):
    """Keep a valid connector or replace its tiny end leg by one chamfer.

    Reflect the short-leg direction about the long leg, so the construction
    commutes with rotations/reflections. No grid walk or clearance search is
    performed here. The caller certifies the entire repaired connector.
    """
    lengths = [calculate_route_length([s]) for s in candidate]
    if candidate and min(lengths) >= minimum_length - 1e-9:
        yield candidate
        return
    if len(candidate) != 2:
        return
    reverse = lengths[0] > lengths[1]
    points = [(candidate[0].start_x, candidate[0].start_y),
              (candidate[0].end_x, candidate[0].end_y),
              (candidate[1].end_x, candidate[1].end_y)]
    if reverse:
        points.reverse()
        lengths.reverse()
    short, long = lengths
    if short <= 1e-9 or long <= 1e-9:
        return
    a, joint, b = points
    def direction(first, last):
        # KRT bends are rounded to four decimals: classify all eight
        # directions equally, then reconstruct from the exact outer anchors.
        angle = round(math.atan2(last[1] - first[1], last[0] - first[0]) /
                      (math.pi / 4)) * (math.pi / 4)
        return math.cos(angle), math.sin(angle)

    u, v = direction(a, joint), direction(joint, b)
    cosine = u[0] * v[0] + u[1] * v[1]
    # Canonical short-leg connectors turn by 45 degrees. Other geometries
    # must be reconsidered with the neighbouring source window instead.
    if abs(cosine - math.sqrt(.5)) > 1e-6:
        return
    dx, dy = b[0] - a[0], b[1] - a[1]
    cross = u[0] * v[1] - u[1] * v[0]
    short = (dx * v[1] - dy * v[0]) / cross
    long = (u[0] * dy - u[1] * dx) / cross
    if short < -1e-7 or short >= minimum_length:
        return
    w = (2 * cosine * v[0] - u[0], 2 * cosine * v[1] - u[1])
    step = minimum_length + 2e-6  # leave room for six-decimal coordinates
    if long - 2 * cosine * step < minimum_length:
        return
    repaired = [a, (a[0] + (short + step) * u[0],
                    a[1] + (short + step) * u[1]),
                (b[0] - step * w[0], b[1] - step * w[1]), b]
    if reverse:
        repaired.reverse()
    repaired[1:-1] = [(round(x, 6), round(y, 6)) for x, y in repaired[1:-1]]
    template = candidate[0]
    result = [Segment(*a, *b, template.width, template.layer, template.net_id)
              for a, b in zip(repaired, repaired[1:])]
    if all(calculate_route_length([s]) >= minimum_length - 1e-9 for s in result):
        yield result
