"""Shared route geometry, independent of optimization stages."""

import math

from .krt_api import (Segment, FP_EPS_MM, pos_key, point_to_pad_distance,
    point_to_segment_distance, segments_intersect)


def _pad_holds_point(pad, point, layer, half_width):
    if layer not in pad.layers and not any("*" in name for name in pad.layers):
        return False
    return point_to_pad_distance(point[0], point[1], pad) <= half_width + 1e-6


def _candidate_segments(a, b, layer, width, net_id):
    """KRT's two shortest connector families, reconstructed at exact anchors.

    The KRT convenience helper rounds bends to four decimals. That changes
    their direction on imported off-grid anchors; no rounding belongs here.
    """
    ax, ay = a
    bx, by = b
    dx, dy = bx-ax, by-ay
    adx, ady = abs(dx), abs(dy)
    sx, sy = (1 if dx >= 0 else -1), (1 if dy >= 0 else -1)
    options = [[]] if _octolinear_points(a, b) else []
    if adx >= ady:
        options += [[(ax+sx*ady, by)], [(bx-sx*ady, ay)]]
    else:
        options += [[(bx, ay+sy*adx)], [(ax, by-sy*adx)]]
    for bends in options:
        candidate = _segments_for_points([a] + bends + [b], layer, width,
                                         net_id)
        if candidate:
            yield candidate


def _octolinear_points(a, b):
    dx, dy = abs(b[0]-a[0]), abs(b[1]-a[1])
    return min(dx, dy, abs(dx-dy)) <= FP_EPS_MM


def _segments_for_points(points, layer, width, net_id):
    return [Segment(start_x=points[i][0], start_y=points[i][1],
                    end_x=points[i + 1][0], end_y=points[i + 1][1],
                    width=width, layer=layer, net_id=net_id)
            for i in range(len(points) - 1)
            if math.dist(points[i], points[i + 1]) > FP_EPS_MM]


def _connector_families(a, b, segment, grid_step):
    """Shared octolinear connectors for chains, pads and junction approaches."""
    yield "canonical", _candidate_segments(
        a, b, segment.layer, segment.width, segment.net_id)
    yield from (("chamfer", family) for family in
                _chamfer_candidate_families(
                    a, b, segment.layer, segment.width, segment.net_id,
                    grid_step))


def _chamfer_candidate_families(a, b, layer, width, net_id, grid_step):
    """Legacy fixed-endpoint octolinear chamfer families.

    The x/y/d labels below describe directions in one board coordinate frame;
    they are not the relational, orientation-neutral segment-slide rule.
    """
    diagonal_max = min(abs(b[0] - a[0]), abs(b[1] - a[1]))
    if diagonal_max <= grid_step + 1e-9:
        return
    # The diagonal must separate the two orthogonal moves.  Any other
    # permutation puts X and Y next to each other and creates a 90-degree
    # corner even though every individual segment is octolinear.
    orders = (("x", "d", "y"), ("y", "d", "x"))

    for order in orders:
        def family(order=order):
            index = 1
            while index * grid_step < diagonal_max - 1e-9:
                yield _chamfer_candidate_at(
                    a, b, layer, width, net_id, grid_step, index, order)
                index += 1
        yield family()


def _chamfer_candidate_at(a, b, layer, width, net_id, grid_step, index,
                          order):
    """Build one legacy chamfer candidate at an integer KRT-grid index."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    adx, ady = abs(dx), abs(dy)
    diagonal = min(adx, ady) - index * grid_step
    if diagonal <= 1e-9:
        return []
    sx = 1.0 if dx >= 0 else -1.0
    sy = 1.0 if dy >= 0 else -1.0
    moves = {
        "x": (sx * (adx - diagonal), 0.0),
        "y": (0.0, sy * (ady - diagonal)),
        "d": (sx * diagonal, sy * diagonal),
    }
    points = [a]
    x, y = a
    for kind in order:
        mx, my = moves[kind]
        if abs(mx) > 1e-9 or abs(my) > 1e-9:
            x, y = x + mx, y + my
            points.append((x, y))
    points[-1] = b
    return _segments_for_points(points, layer, width, net_id)


def _touches_other_same_net(candidate, outside, vias, allowed_ends):
    """Reject a new same-net junction: G3 changes length, never topology."""
    allowed = {pos_key(*point) for point in allowed_ends}
    for new in candidate:
        for old in outside:
            if new.layer != old.layer:
                continue
            # An allowed common endpoint does not authorize retracing copper.
            # Test positive collinear overlap before the endpoint exception.
            dx, dy = new.end_x - new.start_x, new.end_y - new.start_y
            length = math.hypot(dx, dy)
            if length > 1e-9:
                ux, uy = dx / length, dy / length
                offsets = [(old.start_x - new.start_x, old.start_y - new.start_y),
                           (old.end_x - new.start_x, old.end_y - new.start_y)]
                if all(abs(x * uy - y * ux) <= 1e-7 for x, y in offsets):
                    low, high = sorted(x * ux + y * uy for x, y in offsets)
                    if min(length, high) - max(0.0, low) > 1e-7:
                        return True
            if not segments_intersect(new.start_x, new.start_y,
                                      new.end_x, new.end_y,
                                      old.start_x, old.start_y,
                                      old.end_x, old.end_y):
                continue
            shared = ({pos_key(new.start_x, new.start_y),
                       pos_key(new.end_x, new.end_y)} &
                      {pos_key(old.start_x, old.start_y),
                       pos_key(old.end_x, old.end_y)})
            if not shared or not shared.issubset(allowed):
                return True
        for via in vias:
            key = pos_key(via.x, via.y)
            if key in allowed:
                continue
            if point_to_segment_distance(via.x, via.y,
                                         new.start_x, new.start_y,
                                         new.end_x, new.end_y) <= \
                    (getattr(via, "size", 0.0) + new.width) / 2.0:
                return True
    return False


def _edge_directions(segments, start, end):
    """Traversal directions of an ordered graph edge, including reversed input."""
    first, last = segments[0], segments[-1]
    if pos_key(first.start_x, first.start_y) == pos_key(*start):
        first_vector = (first.end_x - first.start_x,
                        first.end_y - first.start_y)
    else:
        first_vector = (first.start_x - first.end_x,
                        first.start_y - first.end_y)
    if pos_key(last.end_x, last.end_y) == pos_key(*end):
        last_vector = (last.end_x - last.start_x,
                       last.end_y - last.start_y)
    else:
        last_vector = (last.start_x - last.end_x,
                       last.start_y - last.end_y)

    def direction(vector):
        return tuple(0 if abs(value) <= 1e-9 else (1 if value > 0 else -1)
                     for value in vector)
    return direction(first_vector), direction(last_vector)


def _right_angle(first, second):
    return first[0] * second[0] + first[1] * second[1] == 0


_DIRECTIONS = ((1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, -1.0))

def _other_end(segment, at):
    if pos_key(segment.start_x, segment.start_y) == at:
        return segment.end_x, segment.end_y
    return segment.start_x, segment.start_y


def _line_intersection(a, u, b, v):
    denominator = u[0] * v[1] - u[1] * v[0]
    if abs(denominator) <= 1e-12:
        return None
    t = ((b[0] - a[0]) * v[1] - (b[1] - a[1]) * v[0]) / denominator
    return a[0] + t * u[0], a[1] + t * u[1]
