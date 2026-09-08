"""Orientation-neutral sliding of one segment between two neighbours.

This module deliberately contains geometry only.  It does not decide whether a
slide is useful for shortening, centering, clearance, or a later transformation.
The caller supplies the scalar translation of the middle segment and owns the
acceptance policy.
"""

from dataclasses import dataclass
import math

from dgloss.krt_api import Segment
from dgloss.krt_api import calculate_route_length


_EPS = 1e-8


@dataclass(frozen=True)
class SegmentSlide:
    """A reconstructed three-segment chain after a parallel translation."""

    source_segments: tuple
    segments: tuple
    offset: float
    before_length: float
    after_length: float


@dataclass(frozen=True)
class SlideInterval:
    """Scalar translations for which no member reverses through an anchor."""

    minimum: float
    maximum: float


def _ends(segment):
    return ((segment.start_x, segment.start_y),
            (segment.end_x, segment.end_y))


def _same_point(first, second, tolerance=_EPS):
    return math.dist(first, second) <= tolerance


def _shared_end(first, second):
    matches = [(a, b) for a in _ends(first) for b in _ends(second)
               if _same_point(a, b)]
    if len(matches) != 1:
        return None
    return matches[0][0]


def _other_end(segment, joint):
    start, end = _ends(segment)
    if _same_point(start, joint):
        return end
    if _same_point(end, joint):
        return start
    return None


def _ordered_geometry(first, middle, last):
    """Return outer-a, joint-a, joint-b, outer-b independent of storage order."""
    joint_a = _shared_end(first, middle)
    joint_b = _shared_end(middle, last)
    if joint_a is None or joint_b is None or _same_point(joint_a, joint_b):
        return None
    if not all(segment.net_id == middle.net_id and
               segment.layer == middle.layer and
               abs(segment.width - middle.width) <= 1e-6
               for segment in (first, last)):
        return None
    outer_a = _other_end(first, joint_a)
    outer_b = _other_end(last, joint_b)
    if outer_a is None or outer_b is None:
        return None
    return outer_a, joint_a, joint_b, outer_b


def _cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def _dot(first, second):
    return first[0] * second[0] + first[1] * second[1]


def _sub(first, second):
    return first[0] - second[0], first[1] - second[1]


def _line_intersection(point_a, vector_a, point_b, vector_b):
    denominator = _cross(vector_a, vector_b)
    if abs(denominator) <= 1e-12:
        return None
    delta = _sub(point_b, point_a)
    scale = _cross(delta, vector_b) / denominator
    return (point_a[0] + scale * vector_a[0],
            point_a[1] + scale * vector_a[1])


def _octolinear(first, second, tolerance=1e-6):
    dx = abs(second[0] - first[0])
    dy = abs(second[1] - first[1])
    return dx <= tolerance or dy <= tolerance or abs(dx - dy) <= tolerance


def _joints_at_offset(geometry, offset):
    outer_a, joint_a, joint_b, outer_b = geometry
    middle_vector = _sub(joint_b, joint_a)
    middle_length = math.hypot(*middle_vector)
    if middle_length <= _EPS:
        return None
    normal = (-middle_vector[1] / middle_length,
              middle_vector[0] / middle_length)
    shifted = (joint_a[0] + offset * normal[0],
               joint_a[1] + offset * normal[1])
    first_vector = _sub(joint_a, outer_a)
    last_vector = _sub(joint_b, outer_b)
    new_a = _line_intersection(outer_a, first_vector,
                               shifted, middle_vector)
    new_b = _line_intersection(outer_b, last_vector,
                               shifted, middle_vector)
    if new_a is None or new_b is None:
        return None
    return new_a, new_b


def slide_segment(first, middle, last, offset, *, minimum_length=0.0):
    """Translate ``middle`` and slide both joints on the neighbour supports.

    The construction is expressed only with support-line intersections.  No
    direction is designated as horizontal, vertical, or diagonal.  ``offset``
    is a signed physical distance along the left normal of the ordered middle
    segment.
    """
    geometry = _ordered_geometry(first, middle, last)
    if geometry is None:
        return None
    outer_a, joint_a, joint_b, outer_b = geometry
    joints = _joints_at_offset(geometry, float(offset))
    if joints is None:
        return None
    new_a, new_b = joints

    old_first = _sub(joint_a, outer_a)
    old_middle = _sub(joint_b, joint_a)
    old_last = _sub(joint_b, outer_b)
    new_first = _sub(new_a, outer_a)
    new_middle = _sub(new_b, new_a)
    new_last = _sub(new_b, outer_b)
    if (_dot(old_first, new_first) < -_EPS or
            _dot(old_middle, new_middle) <= _EPS or
            _dot(old_last, new_last) < -_EPS):
        return None

    points = (outer_a, new_a, new_b, outer_b)
    lengths = [math.dist(points[index], points[index + 1])
               for index in range(3)]
    if any(length < minimum_length - _EPS for length in lengths):
        return None
    if not all(_octolinear(points[index], points[index + 1])
               for index in range(3)):
        return None

    built = tuple(Segment(
        points[index][0], points[index][1],
        points[index + 1][0], points[index + 1][1],
        middle.width, middle.layer, middle.net_id)
        for index in range(3))
    source = (first, middle, last)
    return SegmentSlide(
        source, built, float(offset), calculate_route_length(source),
        calculate_route_length(built))


def slide_length_rate(first, middle, last):
    """Length derivative per signed normal millimetre, before reversal.

    Every member remains on its support with a fixed traversal direction, so
    its length is affine in the offset. None denotes unsupported geometry.
    """
    geometry = _ordered_geometry(first, middle, last)
    if geometry is None:
        return None
    a, b, c, d = geometry
    shifted = _joints_at_offset(geometry, 1.0)
    if shifted is None:
        return None
    vb, vc = _sub(shifted[0], b), _sub(shifted[1], c)
    rate = 0.0
    for vector, velocity in ((_sub(b, a), vb),
                             (_sub(c, b), _sub(vc, vb)),
                             (_sub(c, d), vc)):
        length = math.hypot(*vector)
        if length <= _EPS:
            return None
        rate += _dot(vector, velocity) / length
    return rate


def slide_interval(first, middle, last, *, minimum_length=0.0):
    """Return the full no-reversal interval for the scalar slide."""
    geometry = _ordered_geometry(first, middle, last)
    if geometry is None:
        return None
    base = _joints_at_offset(geometry, 0.0)
    unit = _joints_at_offset(geometry, 1.0)
    if base is None or unit is None:
        return None
    outer_a, joint_a, joint_b, outer_b = geometry
    velocity_a = _sub(unit[0], base[0])
    velocity_b = _sub(unit[1], base[1])

    constraints = []
    for outer, joint, velocity in (
            (outer_a, joint_a, velocity_a),
            (outer_b, joint_b, velocity_b)):
        vector = _sub(joint, outer)
        length = math.hypot(*vector)
        if length <= _EPS:
            return None
        direction = (vector[0] / length, vector[1] / length)
        constraints.append((length, _dot(velocity, direction)))

    middle_vector = _sub(joint_b, joint_a)
    middle_length = math.hypot(*middle_vector)
    middle_direction = (middle_vector[0] / middle_length,
                        middle_vector[1] / middle_length)
    constraints.append((
        middle_length,
        _dot(_sub(velocity_b, velocity_a), middle_direction)))

    lower, upper = -math.inf, math.inf
    for initial, rate in constraints:
        remaining = initial - minimum_length
        if remaining < -_EPS:
            return None
        if abs(rate) <= 1e-12:
            continue
        boundary = -remaining / rate
        if rate > 0.0:
            lower = max(lower, boundary)
        else:
            upper = min(upper, boundary)
    if lower > upper + _EPS:
        return None
    return SlideInterval(lower, upper)
