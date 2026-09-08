"""Geometry of a two-pad gate, using KRT distances and clearances."""

import math
from .krt_api import pad_copper_layers, point_to_pad_distance
from .krt_sweep import pad_axis_distance as _segment_pad_distance


def _intersection(a, b, c, d, eps=1e-9, allow_ab_ends=False):
    """Return (point, parameter on AB, parameter on CD), or ``None``."""
    abx, aby = b[0] - a[0], b[1] - a[1]
    cdx, cdy = d[0] - c[0], d[1] - c[1]
    denominator = abx * cdy - aby * cdx
    if abs(denominator) <= eps:
        return None
    acx, acy = c[0] - a[0], c[1] - a[1]
    t = (acx * cdy - acy * cdx) / denominator
    u = (acx * aby - acy * abx) / denominator
    t_inside = (-eps <= t <= 1.0 + eps if allow_ab_ends else
                eps < t < 1.0 - eps)
    if t_inside and eps < u < 1.0 - eps:
        return ((a[0] + t * abx, a[1] + t * aby), t, u)
    return None


def _edge_towards(pad, target, iterations=42):
    """Pad boundary on the centre-to-target ray, using KRT's pad distance."""
    start = (pad.global_x, pad.global_y)
    if point_to_pad_distance(*start, pad) > 1e-7:
        return None
    if point_to_pad_distance(*target, pad) <= 1e-7:
        return None
    low, high = 0.0, 1.0
    for _ in range(iterations):
        middle = (low + high) / 2.0
        point = (start[0] + middle * (target[0] - start[0]),
                 start[1] + middle * (target[1] - start[1]))
        if point_to_pad_distance(*point, pad) <= 1e-9:
            low = middle
        else:
            high = middle
    return (start[0] + low * (target[0] - start[0]),
            start[1] + low * (target[1] - start[1]))


def _pair_clearance(config, track_net, pad, layer):
    rules = getattr(config, "net_clearances", None) or {}
    value = max(config.clearance, rules.get(track_net, config.clearance),
                rules.get(pad.net_id, config.clearance))
    if hasattr(config, "layer_clearance"):
        value = config.layer_clearance(layer, value)
    return max(value, getattr(pad, "local_clearance", 0.0) or 0.0)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _point(segment, start):
    return ((segment.start_x, segment.start_y) if start else
            (segment.end_x, segment.end_y))


def _other_end(segment, shared):
    start = (segment.start_x, segment.start_y)
    end = (segment.end_x, segment.end_y)
    return end if math.dist(start, shared) <= 1e-7 else start


def _octolinear(a, b, tolerance=1e-7):
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    return dx <= tolerance or dy <= tolerance or abs(dx - dy) <= tolerance


def _native_direction(a, b):
    """Recover an exact direction from endpoints quantized to KiCad's 1 nm.

    Only input classification admits one native unit (plus floating-point
    roundoff). Constructed output still uses strict octolinearity checks.
    Anchors themselves are never snapped or moved by this function.
    """
    dx, dy = b[0]-a[0], b[1]-a[1]
    tolerance = 1e-6 + 8*max(math.ulp(v) for v in (*a, *b))
    if math.hypot(dx, dy) <= tolerance:
        return None
    if abs(dx) <= tolerance:
        return (0., math.copysign(1., dy))
    if abs(dy) <= tolerance:
        return (math.copysign(1., dx), 0.)
    if abs(abs(dx)-abs(dy)) <= tolerance:
        return (math.copysign(1., dx), math.copysign(1., dy))
    return None


def _axis_to_pad_distance(axis, direction, pad):
    """Exact KRT distance from an effectively infinite axis to pad copper."""
    extent = (math.dist(axis, (pad.global_x, pad.global_y)) +
              math.hypot(pad.size_x, pad.size_y) + 1.0)
    start = (axis[0] - direction[0] * extent,
             axis[1] - direction[1] * extent)
    end = (axis[0] + direction[0] * extent,
           axis[1] + direction[1] * extent)
    return _segment_pad_distance(start, end, pad)


def door_crossing_options(door, *, allow_reorientation):
    """Return octolinear directions ordered by decreasing obstacle margin."""
    source_vector = (door.segment.end_x - door.segment.start_x,
                     door.segment.end_y - door.segment.start_y)
    source_length = math.hypot(*source_vector)
    if source_length <= 1e-9:
        return None
    source = (source_vector[0] / source_length,
              source_vector[1] / source_length)
    if not allow_reorientation:
        return (source,)
    diagonal = math.sqrt(0.5)
    orientations = ((1.0, 0.0), (diagonal, diagonal),
                    (0.0, 1.0), (-diagonal, diagonal))

    def same_axis(left, right):
        return abs(abs(left[0] * right[0] + left[1] * right[1]) - 1.0) \
               <= 1e-9

    ranked = []
    for direction in orientations:
        distance_a = _axis_to_pad_distance(door.axis, direction, door.pad_a)
        distance_b = _axis_to_pad_distance(door.axis, direction, door.pad_b)
        margin_a = distance_a - door.segment.width / 2.0 - door.clearance_a
        margin_b = distance_b - door.segment.width / 2.0 - door.clearance_b
        ranked.append((min(margin_a, margin_b),
                       margin_a + margin_b,
                       1 if same_axis(direction, source) else 0,
                       direction))
    ranked.sort(key=lambda item: item[:3], reverse=True)
    return tuple(item[3] for item in ranked)


def door_crossing_direction(door, *, allow_reorientation):
    """Return the locally best octolinear door-crossing direction."""
    options = door_crossing_options(
        door, allow_reorientation=allow_reorientation)
    return options[0] if options else None


def _line_intersection(point_a, vector_a, point_b, vector_b):
    denominator = _cross(vector_a, vector_b)
    if abs(denominator) <= 1e-9:
        return None
    delta = (point_b[0] - point_a[0], point_b[1] - point_a[1])
    scale = _cross(delta, vector_b) / denominator
    return (point_a[0] + scale * vector_a[0],
            point_a[1] + scale * vector_a[1])


def _native_pad_at(pcb_data, net_id, layer, point):
    """Return the fixed native pad terminal at ``point``, if any."""
    copper_layers = list(getattr(pcb_data.board_info, "copper_layers", ()))
    for pad in pcb_data.pads_by_net.get(net_id, ()):
        if layer not in pad_copper_layers(pad, copper_layers):
            continue
        if math.dist((pad.global_x, pad.global_y), point) <= 1e-7:
            return pad
    return None
