"""Continuous distance composition using KRT obstacle shapes and primitives.

KRT's convenience segment/pad functions sample along the axis. For a swept
surface boundary we instead compose its exact capsule/ring distances. Rounded
rectangles are KRT's own inner rectangle plus corner radius, not a new model.
"""
import math
import numpy as np
from .krt_api import (_seg_capsule_axis_dist, _segment_to_rings_distance,
                      point_in_polygon, _foreign_pad_arrays, _pad_corner_radius)


def polygon_axis_distance(x1, y1, x2, y2, polygons):
    if any(point_in_polygon(x1, y1, p) or point_in_polygon(x2, y2, p)
           for p in polygons):
        return 0.
    return _segment_to_rings_distance(x1, y1, x2, y2, polygons)


def rounded_rect_axis_distance(x1, y1, x2, y2, cx, cy, hx, hy, radius, c, s):
    """Vectorized distance to KRT inner rectangles, offset by physical radius."""
    ix, iy = hx-radius, hy-radius
    corners_x = np.asarray([-ix, ix, ix, -ix])
    corners_y = np.asarray([-iy, -iy, iy, iy])
    ax = cx + corners_x*c - corners_y*s
    ay = cy + corners_x*s + corners_y*c
    bx, by = np.roll(ax, -1, axis=0), np.roll(ay, -1, axis=0)
    distance = np.min(_seg_capsule_axis_dist(x1, y1, x2, y2, ax, ay, bx, by), axis=0)
    for x, y in ((x1, y1), (x2, y2)):
        lx, ly = (x-cx)*c+(y-cy)*s, -(x-cx)*s+(y-cy)*c
        distance = np.where((np.abs(lx) <= ix) & (np.abs(ly) <= iy), 0., distance)
    return np.maximum(0., distance-radius)


def pad_axis_distance(start, end, pad):
    if getattr(pad, 'polygons', None):
        return polygon_axis_distance(*start, *end, pad.polygons)
    angle = math.radians(getattr(pad, 'rect_rotation', 0.) or 0.)
    return float(rounded_rect_axis_distance(
        *start, *end, pad.global_x, pad.global_y, pad.size_x/2, pad.size_y/2,
        _pad_corner_radius(pad), math.cos(angle), math.sin(angle)))


def foreign_pad_clearance_distance(pcb, net_id, x1, y1, x2, y2, layer,
                                   effective, net_clearances, half_width):
    """Distance minus KRT rule excess; only physically relevant pads queried.

    Broad-phase bounds include each pad's actual rule and the real track
    radius. There is no arbitrary neighbourhood radius or sampling interval.
    """
    nid, cx, cy, hx, hy, cr, c, s, ex, ey, local, custom = _foreign_pad_arrays(pcb, layer)
    rules = np.maximum(effective, local)
    if net_clearances:
        rules = np.maximum(rules, [net_clearances.get(int(n), effective) for n in nid])
    reach = rules + half_width
    near = ((nid != net_id) & (cx+ex >= min(x1, x2)-reach) &
            (cx-ex <= max(x1, x2)+reach) & (cy+ey >= min(y1, y2)-reach) &
            (cy-ey <= max(y1, y2)+reach))
    best = float('inf')
    if near.any():
        distance = rounded_rect_axis_distance(
            x1, y1, x2, y2, cx[near], cy[near], hx[near], hy[near], cr[near], c[near], s[near])
        best = float(np.min(distance - (rules[near]-effective)))
    for nid, pad in custom:
        if nid != net_id:
            rule = max(effective, getattr(pad, 'local_clearance', 0.) or 0.,
                       (net_clearances or {}).get(nid, effective))
            best = min(best, polygon_axis_distance(x1, y1, x2, y2, pad.polygons) -
                       (rule-effective))
    return best
