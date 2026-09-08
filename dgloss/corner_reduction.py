"""Continuous octolinear corner reductions, stopped by physical obstacles.

Intermediate supports rotate by 45 degrees between the incident directions.
Their common offset from the old corner is the only degree of freedom. The
removed corner caps are nested convex polygons, so their first KRT collision
can be located by bisection (numerical contact solving, not a routing grid).
This is a local family, not a claim of globally shortest corridor routing.
"""
import math

from .execution import perf_counter
from .krt_api import FP_EPS_MM, point_in_polygon
from .route_geometry import (_octolinear_points, _segments_for_points,
                             _touches_other_same_net)


def _intersection(n, h, m, k):
    cross = n[0] * m[1] - n[1] * m[0]
    return ((h * m[1] - n[1] * k) / cross,
            (n[0] * k - h * m[0]) / cross)


def corner_family(points):
    """Unit cap vertices and endpoint-absorption bound; rotation equivariant."""
    a, b, c = points
    if not (_octolinear_points(a, b) and _octolinear_points(b, c)):
        return None
    first, last = math.dist(a, b), math.dist(b, c)
    if min(first, last) <= FP_EPS_MM:
        return None
    u = ((b[0]-a[0])/first, (b[1]-a[1])/first)
    v = ((c[0]-b[0])/last, (c[1]-b[1])/last)
    dot, cross = u[0]*v[0]+u[1]*v[1], u[0]*v[1]-u[1]*v[0]
    # Straight lines, reversals and already gentle (45 degree) joints do not
    # have this convex shortening family. No board axis is privileged.
    if dot > FP_EPS_MM or abs(cross) <= FP_EPS_MM:
        return None
    turn = math.atan2(cross, dot)
    count = round(abs(turn)/(math.pi/4))
    sign = 1 if turn > 0 else -1
    directions = [u]
    for index in range(1, count):
        angle = sign*index*math.pi/4
        co, si = math.cos(angle), math.sin(angle)
        directions.append((u[0]*co-u[1]*si, u[0]*si+u[1]*co))
    directions.append(v)
    normals = [(-sign*d[1], sign*d[0]) for d in directions]
    offsets = [0.] + [1.]*(count-1) + [0.]
    vertices = [_intersection(n, h, m, k) for n, h, m, k in
                zip(normals, offsets, normals[1:], offsets[1:])]
    maximum = min(first/math.hypot(*vertices[0]),
                  last/math.hypot(*vertices[-1]))
    return vertices, maximum


def reduce_corner(context, points, template, deadline=None, *, outside=(), vias=()):
    """Return a certified shorter connector, possibly with more segments.

    Radial expansion of the cap moves both incident contacts together. Every
    intermediate track axis lies in the cap; its boundary and filled triangles
    are certified with the real track width by KRT. The caps are nested, hence
    a blocked cap cannot become reachable again beyond the obstacle.
    """
    family = corner_family(points)
    if family is None:
        return None
    units, maximum = family
    a, corner, c = points
    minimum_length = context.coord.grid_step
    scale = max(math.hypot(*p) for p in units)
    minimum = max(minimum_length/math.dist(p, q)
                  for p, q in zip(units, units[1:]))
    if minimum > maximum:
        return None

    def expired():
        return deadline is not None and perf_counter() >= deadline

    def vertices(radius):
        return [(corner[0]+radius*x, corner[1]+radius*y) for x, y in units]

    def clears(radius):
        cap = vertices(radius)
        # Same-net branches are excluded by the foreign-copper KRT adapter,
        # but cannot be crossed during a reduction either. Check the closed
        # cap boundary and enclosed components, not just the final connector.
        polygon = [corner]+cap
        boundary = _segments_for_points(polygon+[corner], template.layer,
                                        template.width, template.net_id)
        if _touches_other_same_net(boundary, outside, vias, (a, c)):
            return False
        for segment in outside:
            if segment.layer != template.layer:
                continue
            for p in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
                if p not in (a, c) and point_in_polygon(*p, polygon):
                    return False
        if any((v.x, v.y) not in (a, c) and point_in_polygon(v.x, v.y, polygon)
               for v in vias):
            return False
        return all(not expired() and
                   context.clearance_adapter.sweep_triangle_clears(
                       (corner, p, q), template)
                   for p, q in zip(cap, cap[1:]))

    if expired() or not clears(minimum):
        return None
    low, high = minimum, maximum
    if clears(high):
        low = high
    else:
        while (high-low)*scale > FP_EPS_MM:
            if expired():
                return None
            middle = (low+high)/2
            if clears(middle):
                low = middle
            else:
                high = middle

    # A contact must not leave a sub-minimum residual incident leg. Exact
    # endpoint absorption is allowed; otherwise stop at the existing minimum.
    for endpoint, unit in ((a, units[0]), (c, units[-1])):
        speed = math.hypot(*unit)
        remaining = math.dist(endpoint, corner)-low*speed
        if FP_EPS_MM < remaining < minimum_length:
            low = min(low, (math.dist(endpoint, corner)-minimum_length)/speed)
    if low < minimum or expired():
        return None
    cap = vertices(low)
    if math.dist(cap[0], a) <= FP_EPS_MM:
        cap[0] = a
    if math.dist(cap[-1], c) <= FP_EPS_MM:
        cap[-1] = c
    candidate = _segments_for_points([a]+cap+[c], template.layer,
                                     template.width, template.net_id)
    if (not candidate or
            any(math.dist((s.start_x, s.start_y), (s.end_x, s.end_y)) <
                minimum_length-FP_EPS_MM for s in candidate) or
            not all(_octolinear_points((s.start_x, s.start_y),
                                      (s.end_x, s.end_y)) for s in candidate) or
            not context.clearance_adapter.connector_clears(candidate)):
        return None
    return candidate
