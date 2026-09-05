"""G3.6: detect and center tracks crossing two-pad gates.

KRT owns pad geometry, copper-layer expansion and the spatial index.  This
module combines those existing operations and integrates accepted candidates
into dgloss; it does not implement a new Rust primitive.
"""

from dataclasses import dataclass
import heapq
import math
from time import perf_counter

from check_connected import check_net_connectivity
from check_drc import (SpatialIndex, _segment_to_polys_distance,
                       pad_copper_layers, point_to_pad_distance,
                       segment_to_rect_distance)
from kicad_parser import Segment

from .changes import GlossChanges, release_result_custody


@dataclass(frozen=True)
class InterpadDoor:
    pad_a: object
    pad_b: object
    segment: object
    layer: str
    crossing: tuple
    axis: tuple
    edge_a: tuple
    edge_b: tuple
    clearance_a: float
    clearance_b: float
    proximity_mm: float
    distance_a: float
    distance_b: float
    copper_gap: float
    admissible_width: float
    offset: float


@dataclass(frozen=True)
class InterpadScan:
    doors: tuple
    elapsed_ms: float
    pad_pairs: int
    geometric_gates: int
    unique_crossings: int


@dataclass(frozen=True)
class InterpadCandidate:
    source_segments: tuple
    segments: tuple
    translation: tuple
    before_length: float
    after_length: float


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


def _axis_to_pad_distance(axis, direction, pad):
    """Exact KRT distance from an effectively infinite axis to pad copper."""
    extent = (math.dist(axis, (pad.global_x, pad.global_y)) +
              math.hypot(pad.size_x, pad.size_y) + 1.0)
    start = (axis[0] - direction[0] * extent,
             axis[1] - direction[1] * extent)
    end = (axis[0] + direction[0] * extent,
           axis[1] + direction[1] * extent)
    polygons = getattr(pad, "polygons", None)
    if polygons:
        distance, _closest = _segment_to_polys_distance(
            start[0], start[1], end[0], end[1], polygons)
        return distance

    rotation = getattr(pad, "rect_rotation", 0.0) or 0.0
    if rotation:
        radians = math.radians(rotation)
        cosine, sine = math.cos(radians), math.sin(radians)

        def into_frame(point):
            dx = point[0] - pad.global_x
            dy = point[1] - pad.global_y
            return (pad.global_x + dx * cosine + dy * sine,
                    pad.global_y - dx * sine + dy * cosine)

        start, end = into_frame(start), into_frame(end)
    if pad.shape in ("circle", "oval"):
        corner_radius = min(pad.size_x, pad.size_y) / 2.0
    elif pad.shape == "roundrect":
        corner_radius = (getattr(pad, "roundrect_rratio", 0.0) or 0.0) * \
                        min(pad.size_x, pad.size_y)
    else:
        corner_radius = 0.0
    distance, _closest = segment_to_rect_distance(
        start[0], start[1], end[0], end[1],
        pad.global_x, pad.global_y, pad.size_x / 2.0, pad.size_y / 2.0,
        corner_radius)
    return distance


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


def center_with_sliding_neighbors(pcb_data, door, *,
                                  build_new_segments=False):
    """Center one segment using its sliding rails and fixed pad terminals.

    This is the smallest complete M01 construction. It accepts either two
    sliding neighbours, or one fixed native pad and one sliding neighbour.
    The chain must remain simple, same-layer and octolinear. The returned
    objects are new KRT ``Segment`` instances; the PCBData is never mutated.
    When ``build_new_segments`` is false, a construction that would increase
    the number of segments is not returned.
    """
    source = door.segment
    if getattr(source, "locked", False):
        return None
    a = (source.start_x, source.start_y)
    b = (source.end_x, source.end_y)
    direction = (b[0] - a[0], b[1] - a[1])
    if not _octolinear(a, b) or math.hypot(*direction) <= 1e-9:
        return None

    def neighbours(point):
        found = []
        for segment in pcb_data.segments:
            if segment is source or segment.net_id != source.net_id or \
                    segment.layer != source.layer or \
                    getattr(segment, "graphic", False) or \
                    getattr(segment, "locked", False):
                continue
            if (math.dist((segment.start_x, segment.start_y), point) <= 1e-7 or
                    math.dist((segment.end_x, segment.end_y), point) <= 1e-7):
                found.append(segment)
        return found

    translation = (door.axis[0] - door.crossing[0],
                   door.axis[1] - door.crossing[1])

    def make(start, end, template):
        if math.dist(start, end) <= 1e-7:
            return None
        return Segment(start[0], start[1], end[0], end[1], template.width,
                       template.layer, template.net_id)

    at_a, at_b = neighbours(a), neighbours(b)
    if len(at_a) == len(at_b) == 1 and at_a[0] is not at_b[0]:
        first, last = at_a[0], at_b[0]
        outer_a, outer_b = _other_end(first, a), _other_end(last, b)
        rail_a = (a[0] - outer_a[0], a[1] - outer_a[1])
        rail_b = (b[0] - outer_b[0], b[1] - outer_b[1])
        if math.hypot(*rail_a) <= 1e-9 or math.hypot(*rail_b) <= 1e-9 or \
                not (_octolinear(outer_a, a) and
                     _octolinear(outer_b, b)):
            return None

        # The new source line is parallel to the old one and passes through
        # the weighted door axis. Its intersections with both neighbour lines
        # are the new sliding joints.
        new_a = _line_intersection(
            door.axis, direction, outer_a, rail_a)
        new_b = _line_intersection(
            door.axis, direction, outer_b, rail_b)
        if new_a is None or new_b is None:
            return None
        if ((new_b[0] - new_a[0]) * direction[0] +
                (new_b[1] - new_a[1]) * direction[1] <= 1e-9):
            return None

        # A rail may disappear at its outer anchor, but it may not reverse.
        for outer, old, new in ((outer_a, a, new_a),
                                (outer_b, b, new_b)):
            old_vector = (old[0] - outer[0], old[1] - outer[1])
            new_vector = (new[0] - outer[0], new[1] - outer[1])
            if (old_vector[0] * new_vector[0] +
                    old_vector[1] * new_vector[1] < -1e-8):
                return None

        built = [make(outer_a, new_a, first),
                 make(new_a, new_b, source),
                 make(new_b, outer_b, last)]
        old = (first, source, last)
    else:
        # A track which starts at a fixed pad and has one sliding neighbour
        # needs one new octolinear connection at the pad. This is the smallest
        # useful form exposed by test_centering1: fixed pad, centered parallel,
        # then the existing neighbour rail.
        if not build_new_segments:
            return None
        cases = []
        if (not at_a and len(at_b) == 1 and
                _native_pad_at(pcb_data, source.net_id, source.layer, a)):
            cases.append((a, b, at_b[0]))
        if (not at_b and len(at_a) == 1 and
                _native_pad_at(pcb_data, source.net_id, source.layer, b)):
            cases.append((b, a, at_a[0]))
        if len(cases) != 1:
            return None

        fixed, joint, neighbour = cases[0]
        outer = _other_end(neighbour, joint)
        source_vector = (joint[0] - fixed[0], joint[1] - fixed[1])
        rail = (joint[0] - outer[0], joint[1] - outer[1])
        if not _octolinear(outer, joint) or math.hypot(*rail) <= 1e-9:
            return None
        new_joint = _line_intersection(
            door.axis, source_vector, outer, rail)
        if new_joint is None:
            return None
        old_rail = (joint[0] - outer[0], joint[1] - outer[1])
        new_rail = (new_joint[0] - outer[0], new_joint[1] - outer[1])
        if old_rail[0] * new_rail[0] + old_rail[1] * new_rail[1] < -1e-8:
            return None

        alternatives = []
        for connector_direction in ((1.0, 0.0), (0.0, 1.0),
                                    (1.0, 1.0), (1.0, -1.0)):
            new_fixed = _line_intersection(
                fixed, connector_direction, door.axis, source_vector)
            if new_fixed is None:
                continue
            centered = (new_joint[0] - new_fixed[0],
                        new_joint[1] - new_fixed[1])
            if centered[0] * source_vector[0] + \
                    centered[1] * source_vector[1] <= 1e-9:
                continue
            candidate_segments = [
                make(fixed, new_fixed, source),
                make(new_fixed, new_joint, source),
                make(new_joint, outer, neighbour),
            ]
            candidate_segments = tuple(
                segment for segment in candidate_segments
                if segment is not None)
            if (not candidate_segments or
                    not all(_octolinear(
                        (segment.start_x, segment.start_y),
                        (segment.end_x, segment.end_y))
                            for segment in candidate_segments)):
                continue
            from net_queries import calculate_route_length
            alternatives.append((calculate_route_length(candidate_segments),
                                 candidate_segments))
        if not alternatives:
            return None
        _length, selected = min(
            alternatives, key=lambda item: (item[0], len(item[1])))
        built = list(selected)
        old = (source, neighbour)

    built = tuple(segment for segment in built if segment is not None)
    if not built or (not build_new_segments and len(built) > len(old)) or \
            not all(_octolinear(
            (segment.start_x, segment.start_y),
            (segment.end_x, segment.end_y)) for segment in built):
        return None

    from net_queries import calculate_route_length
    return InterpadCandidate(
        old, built, translation, calculate_route_length(old),
        calculate_route_length(built))


def center_across_multiple_doors(pcb_data, doors, *,
                                 build_new_segments=False):
    """Center one segment successively across two or more ordered doors.

    All doors must cross the same octolinear segment.  Its two neighbouring
    rails slide to the first and last centered parallel, while one shortest
    octolinear transition joins each pair of successive parallels.  For two
    distinct door axes this changes a three-segment chain into five segments.
    """
    doors = tuple(doors)
    if len(doors) < 2:
        return None
    source = doors[0].segment
    if any(door.segment is not source for door in doors) or \
            getattr(source, "locked", False):
        return None
    a = (source.start_x, source.start_y)
    b = (source.end_x, source.end_y)
    direction = (b[0] - a[0], b[1] - a[1])
    length = math.hypot(*direction)
    if length <= 1e-9 or not _octolinear(a, b):
        return None
    tangent = (direction[0] / length, direction[1] / length)
    normal = (-tangent[1], tangent[0])

    def neighbours(point):
        return [segment for segment in pcb_data.segments
                if segment is not source and segment.net_id == source.net_id
                and segment.layer == source.layer
                and not getattr(segment, "graphic", False)
                and not getattr(segment, "locked", False)
                and (math.dist((segment.start_x, segment.start_y), point)
                     <= 1e-7 or
                     math.dist((segment.end_x, segment.end_y), point)
                     <= 1e-7)]

    at_a, at_b = neighbours(a), neighbours(b)
    if len(at_a) != 1 or len(at_b) != 1 or at_a[0] is at_b[0]:
        return None
    first, last = at_a[0], at_b[0]
    outer_a, outer_b = _other_end(first, a), _other_end(last, b)
    rail_a = (a[0] - outer_a[0], a[1] - outer_a[1])
    rail_b = (b[0] - outer_b[0], b[1] - outer_b[1])
    if min(math.hypot(*rail_a), math.hypot(*rail_b)) <= 1e-9 or \
            not (_octolinear(outer_a, a) and _octolinear(outer_b, b)):
        return None

    ordered = sorted(doors, key=lambda door:
                     (door.axis[0] - a[0]) * tangent[0] +
                     (door.axis[1] - a[1]) * tangent[1])
    axes = [(door.axis[0] * tangent[0] + door.axis[1] * tangent[1],
             door.axis[0] * normal[0] + door.axis[1] * normal[1])
            for door in ordered]
    if any(axes[index + 1][0] - axes[index][0] <= 1e-7
           for index in range(len(axes) - 1)):
        return None

    new_a = _line_intersection(ordered[0].axis, direction,
                               outer_a, rail_a)
    new_b = _line_intersection(ordered[-1].axis, direction,
                               outer_b, rail_b)
    if new_a is None or new_b is None:
        return None
    start_u = new_a[0] * tangent[0] + new_a[1] * tangent[1]
    end_u = new_b[0] * tangent[0] + new_b[1] * tangent[1]
    if start_u > axes[0][0] + 1e-7 or end_u < axes[-1][0] - 1e-7:
        return None

    def at(u, q):
        return (tangent[0] * u + normal[0] * q,
                tangent[1] * u + normal[1] * q)

    def make(start, end, template):
        if math.dist(start, end) <= 1e-7:
            return None
        return Segment(start[0], start[1], end[0], end[1], template.width,
                       template.layer, template.net_id)

    inner = []
    current = new_a
    for index in range(len(axes) - 1):
        current_u, current_q = axes[index]
        next_u, next_q = axes[index + 1]
        delta_q = next_q - current_q
        if abs(delta_q) <= 1e-7:
            continue
        transitions = []
        for vector in ((1.0, 0.0), (0.0, 1.0),
                       (1.0, 1.0), (1.0, -1.0)):
            normal_step = vector[0] * normal[0] + vector[1] * normal[1]
            if abs(normal_step) <= 1e-9:
                continue
            scale = delta_q / normal_step
            step = (vector[0] * scale, vector[1] * scale)
            delta_u = step[0] * tangent[0] + step[1] * tangent[1]
            if delta_u <= 1e-7 or delta_u > next_u - current_u + 1e-7:
                continue
            transitions.append((delta_u, step))
        if not transitions:
            return None
        delta_u, step = min(transitions, key=lambda item: item[0])
        transition_start_u = (current_u + next_u - delta_u) / 2.0
        transition_end_u = transition_start_u + delta_u
        transition_start = at(transition_start_u, current_q)
        transition_end = (transition_start[0] + step[0],
                          transition_start[1] + step[1])
        inner.extend((make(current, transition_start, source),
                      make(transition_start, transition_end, source)))
        current = transition_end
    inner.append(make(current, new_b, source))

    built = tuple(segment for segment in
                  [make(outer_a, new_a, first), *inner,
                   make(new_b, outer_b, last)] if segment is not None)
    old = (first, source, last)
    if not built or (not build_new_segments and len(built) > len(old)) or \
            not all(_octolinear((segment.start_x, segment.start_y),
                                (segment.end_x, segment.end_y))
                    for segment in built):
        return None
    from net_queries import calculate_route_length
    translation = (ordered[0].axis[0] - ordered[0].crossing[0],
                   ordered[0].axis[1] - ordered[0].crossing[1])
    return InterpadCandidate(
        old, built, translation, calculate_route_length(old),
        calculate_route_length(built))


def center_across_branch_doors(pcb_data, doors, *,
                               build_new_segments=False,
                               crossing_directions=None):
    """Build one continuous centered path across a simple multi-segment branch.

    Every door contributes its centered line. Consecutive non-parallel lines
    meet directly; shifted parallel lines are joined by the shortest forward
    octolinear transition. Branch endpoints remain fixed.
    """
    doors = tuple(doors)
    if len(doors) < 2:
        return None
    net_id = doors[0].segment.net_id
    layer = doors[0].segment.layer
    width = doors[0].segment.width
    if any(door.segment.net_id != net_id or door.segment.layer != layer or
           abs(door.segment.width - width) > 1e-9 for door in doors):
        return None

    candidates = [segment for segment in pcb_data.segments
                  if segment.net_id == net_id and segment.layer == layer and
                  not getattr(segment, "graphic", False)]

    def key(point):
        return (round(point[0], 7), round(point[1], 7))

    endpoints = {}
    for segment in candidates:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            endpoints.setdefault(key(point), []).append(segment)
    seed = doors[0].segment
    component, pending = set(), [seed]
    while pending:
        segment = pending.pop()
        if id(segment) in component:
            continue
        component.add(id(segment))
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            pending.extend(endpoints.get(key(point), ()))
    chain = [segment for segment in candidates if id(segment) in component]
    if any(id(door.segment) not in component for door in doors) or \
            any(getattr(segment, "locked", False) for segment in chain):
        return None
    chain_endpoints = {}
    for segment in chain:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            chain_endpoints.setdefault(key(point), []).append(segment)
    if any(len(items) > 2 for items in chain_endpoints.values()):
        return None
    ends = [point for point, items in chain_endpoints.items()
            if len(items) == 1]
    if len(ends) != 2:
        return None
    ends.sort(key=lambda point: min(
        math.dist(point, door.crossing) for door in doors))

    ordered_segments = []
    oriented = []
    current_key = ends[0]
    previous = None
    while len(ordered_segments) < len(chain):
        choices = [segment for segment in chain_endpoints[current_key]
                   if segment is not previous]
        if len(choices) != 1:
            return None
        segment = choices[0]
        start = (segment.start_x, segment.start_y)
        end = (segment.end_x, segment.end_y)
        if key(start) != current_key:
            start, end = end, start
        ordered_segments.append(segment)
        oriented.append((start, end))
        previous = segment
        current_key = key(end)

    position = {id(segment): index
                for index, segment in enumerate(ordered_segments)}
    ordered_doors = sorted(
        doors, key=lambda door: (
            position[id(door.segment)],
            (door.crossing[0] - oriented[position[id(door.segment)]][0][0]) *
            (oriented[position[id(door.segment)]][1][0] -
             oriented[position[id(door.segment)]][0][0]) +
            (door.crossing[1] - oriented[position[id(door.segment)]][0][1]) *
            (oriented[position[id(door.segment)]][1][1] -
             oriented[position[id(door.segment)]][0][1])))

    constraints = []
    for door in ordered_doors:
        index = position[id(door.segment)]
        start, end = oriented[index]
        vector = (end[0] - start[0], end[1] - start[1])
        norm = math.hypot(*vector)
        if norm <= 1e-9 or not _octolinear(start, end):
            return None
        original_direction = (vector[0] / norm, vector[1] / norm)
        selected_direction = ((crossing_directions or {}).get(id(door)) or
                              door_crossing_direction(
                                  door,
                                  allow_reorientation=build_new_segments))
        if selected_direction is None:
            return None
        if selected_direction[0] * original_direction[0] + \
                selected_direction[1] * original_direction[1] < 0:
            selected_direction = (-selected_direction[0],
                                  -selected_direction[1])
        constraints.append((door, door.axis, selected_direction))

    allowed = ((1.0, 0.0), (0.0, 1.0),
               (1.0, 1.0), (1.0, -1.0))

    def endpoint_join(anchor, constraint, before, preferred):
        _door, axis, direction = constraint
        found = []
        if abs(_cross((anchor[0] - axis[0], anchor[1] - axis[1]),
                      direction)) <= 1e-8:
            found.append((0, 0.0, anchor))
        for connector in allowed:
            point = _line_intersection(anchor, connector, axis, direction)
            if point is None:
                continue
            along = ((axis[0] - point[0]) * direction[0] +
                     (axis[1] - point[1]) * direction[1])
            if (before and along < -1e-7) or (not before and along > 1e-7):
                continue
            progress = (((point[0] - anchor[0]) * direction[0] +
                         (point[1] - anchor[1]) * direction[1]) if before else
                        ((anchor[0] - point[0]) * direction[0] +
                         (anchor[1] - point[1]) * direction[1]))
            distance = math.dist(anchor, point)
            if distance > 1e-7 and progress <= 1e-7:
                continue
            keeps_terminal = abs(_cross(connector, preferred)) <= 1e-9
            found.append((0 if keeps_terminal else 1, distance, point))
        return min(found, key=lambda item: item[:2])[2] if found else None

    branch_start = oriented[0][0]
    branch_end = oriented[-1][1]
    first_terminal = (oriented[0][1][0] - oriented[0][0][0],
                      oriented[0][1][1] - oriented[0][0][1])
    last_terminal = (oriented[-1][1][0] - oriented[-1][0][0],
                     oriented[-1][1][1] - oriented[-1][0][1])
    entry = endpoint_join(branch_start, constraints[0], True,
                          first_terminal)
    exit_point = endpoint_join(branch_end, constraints[-1], False,
                               last_terminal)
    if entry is None or exit_point is None:
        return None

    points = [branch_start, entry]
    for index in range(len(constraints) - 1):
        _door_a, axis_a, direction_a = constraints[index]
        _door_b, axis_b, direction_b = constraints[index + 1]
        crossing = _line_intersection(axis_a, direction_a,
                                      axis_b, direction_b)
        if crossing is not None:
            after_a = ((crossing[0] - axis_a[0]) * direction_a[0] +
                       (crossing[1] - axis_a[1]) * direction_a[1])
            before_b = ((axis_b[0] - crossing[0]) * direction_b[0] +
                        (axis_b[1] - crossing[1]) * direction_b[1])
            if after_a < -1e-7 or before_b < -1e-7:
                return None
            points.append(crossing)
            continue

        if direction_a[0] * direction_b[0] + \
                direction_a[1] * direction_b[1] < 1.0 - 1e-7:
            return None
        normal = (-direction_a[1], direction_a[0])
        u_a = axis_a[0] * direction_a[0] + axis_a[1] * direction_a[1]
        u_b = axis_b[0] * direction_a[0] + axis_b[1] * direction_a[1]
        q_a = axis_a[0] * normal[0] + axis_a[1] * normal[1]
        q_b = axis_b[0] * normal[0] + axis_b[1] * normal[1]
        if u_b - u_a <= 1e-7:
            return None
        if abs(q_b - q_a) <= 1e-7:
            continue
        transitions = []
        for vector in allowed:
            normal_step = vector[0] * normal[0] + vector[1] * normal[1]
            if abs(normal_step) <= 1e-9:
                continue
            scale = (q_b - q_a) / normal_step
            step = (vector[0] * scale, vector[1] * scale)
            delta_u = step[0] * direction_a[0] + step[1] * direction_a[1]
            if 1e-7 < delta_u <= u_b - u_a + 1e-7:
                transitions.append((delta_u, step))
        if not transitions:
            return None
        delta_u, step = min(transitions, key=lambda item: item[0])
        start_u = (u_a + u_b - delta_u) / 2.0
        transition_start = (direction_a[0] * start_u + normal[0] * q_a,
                            direction_a[1] * start_u + normal[1] * q_a)
        transition_end = (transition_start[0] + step[0],
                          transition_start[1] + step[1])
        points.extend((transition_start, transition_end))
    points.extend((exit_point, branch_end))

    compact = []
    for point in points:
        if not compact or math.dist(compact[-1], point) > 1e-7:
            compact.append(point)
    changed = True
    while changed and len(compact) >= 3:
        changed = False
        reduced = [compact[0]]
        for index in range(1, len(compact) - 1):
            left, middle, right = reduced[-1], compact[index], compact[index + 1]
            first_vector = (middle[0] - left[0], middle[1] - left[1])
            second_vector = (right[0] - middle[0], right[1] - middle[1])
            if abs(_cross(first_vector, second_vector)) <= 1e-8 and \
                    first_vector[0] * second_vector[0] + \
                    first_vector[1] * second_vector[1] >= 0:
                changed = True
                continue
            reduced.append(middle)
        reduced.append(compact[-1])
        compact = reduced

    built = tuple(Segment(start[0], start[1], end[0], end[1], width,
                          layer, net_id)
                  for start, end in zip(compact, compact[1:])
                  if math.dist(start, end) > 1e-7)
    if not built or (not build_new_segments and len(built) > len(chain)) or \
            not all(_octolinear((segment.start_x, segment.start_y),
                                (segment.end_x, segment.end_y))
                    for segment in built):
        return None
    from net_queries import calculate_route_length
    first_door = ordered_doors[0]
    translation = (first_door.axis[0] - first_door.crossing[0],
                   first_door.axis[1] - first_door.crossing[1])
    return InterpadCandidate(
        tuple(chain), built, translation, calculate_route_length(chain),
        calculate_route_length(built))


def find_interpad_doors(pcb_data, config, *, net_id=None,
                        proximity_mm=1.0, deadline=None,
                        allowed_segment_ids=None):
    """Find simple two-pad gates crossed by exactly one track segment.

    The measured interval is the space between the real KRT pad boundaries.
    Its axis is the midpoint after applying the clearance independently on
    each side.  A gate is returned only when the sole crossing segment still
    fits at its current width. At least one obstacle must be strictly closer
    to the segment than ``proximity_mm`` and the copper gap must be strictly
    smaller than ``2 * proximity_mm``. The gate must cross the track. The
    function is read-only; zero proximity deliberately returns no doors.
    """
    if not 0.0 <= proximity_mm <= 5.0:
        raise ValueError("proximity_mm must be between 0 and 5 mm")
    started = perf_counter()
    if proximity_mm == 0:
        return InterpadScan((), (perf_counter() - started) * 1000.0,
                            0, 0, 0)
    copper_layers = list(pcb_data.board_info.copper_layers or config.layers)
    segments = [segment for segment in pcb_data.segments
                if not getattr(segment, "graphic", False)]
    max_track_width = max((segment.width for segment in segments), default=0.0)
    max_pad_radius = max((max(pad.size_x, pad.size_y) / 2.0
                          for net_pads in pcb_data.pads_by_net.values()
                          for pad in net_pads), default=0.0)
    # This only sizes KRT's broad-phase cells.  The semantic cutoff below is
    # pair-specific and uses the actual segment and effective clearances.
    cell_size = max(1.0, 2.0 * proximity_mm + max_track_width +
                    max_pad_radius)
    index = SpatialIndex(cell_size=cell_size)
    for segment in segments:
        index.add_segment(segment, segment.net_id)

    pads = []
    for pad_net, net_pads in pcb_data.pads_by_net.items():
        for pad in net_pads:
            if getattr(pad, "pad_type", "") == "np_thru_hole":
                continue
            layers = pad_copper_layers(pad, copper_layers)
            if not layers:
                continue
            pads.append(pad)
            index.add_pad(pad, pad_net, list(layers))

    # Restrict candidate discovery to the requested net as soon as one has
    # been selected.  The complete segment index remains necessary to prove
    # that no second track crosses a nominated gate.
    candidate_pairs = {}
    seeds = [segment for segment in segments
             if (net_id is None or segment.net_id == net_id) and
             (allowed_segment_ids is None or
              id(segment) in allowed_segment_ids)]
    for seed in seeds:
        if deadline is not None and perf_counter() >= deadline:
            break
        nearby = index.get_nearby_pads_for_segment(seed)
        for first_index, (pad_a, _net_a) in enumerate(nearby):
            for pad_b, _net_b in nearby[first_index + 1:]:
                if pad_a is pad_b:
                    continue
                if seed.layer not in pad_copper_layers(pad_a, copper_layers) or \
                        seed.layer not in pad_copper_layers(pad_b, copper_layers):
                    continue
                key = (min(id(pad_a), id(pad_b)),
                       max(id(pad_a), id(pad_b)), seed.layer)
                candidate_pairs[key] = (pad_a, pad_b, seed.layer)

    doors = []
    pad_pairs = geometric_gates = unique_crossings = 0
    for pad_a, pad_b, layer in candidate_pairs.values():
        if deadline is not None and perf_counter() >= deadline:
            break
        ca = (pad_a.global_x, pad_a.global_y)
        cb = (pad_b.global_x, pad_b.global_y)
        centre_distance = math.dist(ca, cb)
        if centre_distance <= 1e-9:
            continue
        pad_pairs += 1
        edge_a = _edge_towards(pad_a, cb)
        edge_b = _edge_towards(pad_b, ca)
        if edge_a is None or edge_b is None:
            continue
        copper_gap = math.dist(edge_a, edge_b)
        if copper_gap <= 1e-6:
            continue
        geometric_gates += 1
        gate = Segment(edge_a[0], edge_a[1], edge_b[0], edge_b[1],
                       0.0, layer, 0)
        crossings = []
        for segment, _segment_net in index.get_nearby_segments(gate):
            hit = _intersection(
                (segment.start_x, segment.start_y),
                (segment.end_x, segment.end_y), edge_a, edge_b,
                allow_ab_ends=True)
            if hit is not None:
                crossings.append((segment, hit))
        if len(crossings) != 1:
            continue
        segment, (crossing, _track_t, _gate_t) = crossings[0]
        if net_id is not None and segment.net_id != net_id:
            continue
        if (allowed_segment_ids is not None and
                id(segment) not in allowed_segment_ids):
            continue
        unique_crossings += 1
        clearance_a = _pair_clearance(config, segment.net_id, pad_a, layer)
        clearance_b = _pair_clearance(config, segment.net_id, pad_b, layer)
        distance_a = math.dist(edge_a, crossing)
        distance_b = math.dist(edge_b, crossing)
        if (distance_a + 1e-9 >= proximity_mm and
                distance_b + 1e-9 >= proximity_mm):
            continue
        if copper_gap + 1e-9 >= 2.0 * proximity_mm:
            continue
        admissible_width = copper_gap - clearance_a - clearance_b
        if admissible_width + 1e-9 < segment.width:
            continue
        ux = (edge_b[0] - edge_a[0]) / copper_gap
        uy = (edge_b[1] - edge_a[1]) / copper_gap
        left = (edge_a[0] + ux * clearance_a,
                edge_a[1] + uy * clearance_a)
        right = (edge_b[0] - ux * clearance_b,
                 edge_b[1] - uy * clearance_b)
        axis = ((left[0] + right[0]) / 2.0,
                (left[1] + right[1]) / 2.0)
        offset = (axis[0] - crossing[0]) * ux + \
                 (axis[1] - crossing[1]) * uy
        doors.append(InterpadDoor(
            pad_a, pad_b, segment, layer, crossing, axis, edge_a, edge_b,
            clearance_a, clearance_b, proximity_mm, distance_a,
            distance_b, copper_gap, admissible_width, offset))

    elapsed_ms = (perf_counter() - started) * 1000.0
    return InterpadScan(tuple(doors), elapsed_ms, pad_pairs,
                        geometric_gates, unique_crossings)


def _door_key(door):
    pads = sorted((id(door.pad_a), id(door.pad_b)))
    return pads[0], pads[1], door.layer


def _branch_door_groups(pcb_data, doors):
    """Group doors by their same-layer connected track component."""
    by_layer = {}
    for door in doors:
        by_layer.setdefault(door.layer, []).append(door)
    groups = []
    for layer_doors in by_layer.values():
        segments = [segment for segment in pcb_data.segments
                    if segment.net_id == layer_doors[0].segment.net_id and
                    segment.layer == layer_doors[0].layer and
                    not getattr(segment, "graphic", False)]

        def key(point):
            return round(point[0], 7), round(point[1], 7)

        incidence = {}
        for segment in segments:
            for point in ((segment.start_x, segment.start_y),
                          (segment.end_x, segment.end_y)):
                incidence.setdefault(key(point), []).append(segment)
        component_by_id = {}
        component = 0
        for seed in segments:
            if id(seed) in component_by_id:
                continue
            component += 1
            pending = [seed]
            while pending:
                segment = pending.pop()
                if id(segment) in component_by_id:
                    continue
                component_by_id[id(segment)] = component
                for point in ((segment.start_x, segment.start_y),
                              (segment.end_x, segment.end_y)):
                    pending.extend(incidence.get(key(point), ()))
        grouped = {}
        for door in layer_doors:
            grouped.setdefault(component_by_id.get(id(door.segment)), []).append(
                door)
        groups.extend(tuple(group) for group in grouped.values()
                      if len(group) >= 2)
    groups.sort(key=lambda group: (
        len(group), sum(abs(door.offset) for door in group)), reverse=True)
    return groups


def _connected_segment_ids(pcb_data, seeds):
    """Return the same-net/layer component containing ``seeds``."""
    seeds = tuple(seeds)
    if not seeds:
        return set()
    net_id, layer = seeds[0].net_id, seeds[0].layer
    segments = [segment for segment in pcb_data.segments
                if segment.net_id == net_id and segment.layer == layer and
                not getattr(segment, "graphic", False)]

    def key(point):
        return round(point[0], 7), round(point[1], 7)

    incidence = {}
    for segment in segments:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            incidence.setdefault(key(point), []).append(segment)
    found = set()
    pending = list(seeds)
    while pending:
        segment = pending.pop()
        if id(segment) in found:
            continue
        found.add(id(segment))
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            pending.extend(incidence.get(key(point), ()))
    return found


def _ranked_direction_maps(doors, build_new_segments, limit=64):
    """Yield the best joint orientation choices without a Cartesian blow-up."""
    options = [door_crossing_options(
        door, allow_reorientation=build_new_segments) for door in doors]
    if not options or any(not values for values in options):
        return
    initial = tuple(0 for _ in options)
    pending = [(0, initial)]
    seen = {initial}
    emitted = 0
    while pending and emitted < limit:
        _rank, indices = heapq.heappop(pending)
        yield {id(door): options[index][choice]
               for index, (door, choice) in enumerate(zip(doors, indices))}
        emitted += 1
        for index, values in enumerate(options):
            if indices[index] + 1 >= len(values):
                continue
            neighbour = list(indices)
            neighbour[index] += 1
            neighbour = tuple(neighbour)
            if neighbour in seen:
                continue
            seen.add(neighbour)
            heapq.heappush(pending, (sum(neighbour), neighbour))


def _segment_set_signature(segments):
    rows = []
    for segment in segments:
        start = (round(segment.start_x, 7), round(segment.start_y, 7))
        end = (round(segment.end_x, 7), round(segment.end_y, 7))
        rows.append((min(start, end), max(start, end),
                     round(segment.width, 7), segment.layer, segment.net_id))
    return sorted(rows)


def _candidate_is_valid(context, candidate, before_grade):
    """Apply the common editability, geometry, KRT and topology gates."""
    if not context.segments_editable(candidate.source_segments):
        return False, None
    if _segment_set_signature(candidate.source_segments) == \
            _segment_set_signature(candidate.segments):
        return False, None
    if any(math.hypot(segment.end_x - segment.start_x,
                      segment.end_y - segment.start_y) <
           context.coord.grid_step - 1e-9
           for segment in candidate.segments):
        return False, None
    if not context.clearance_adapter.connector_clears(candidate.segments):
        return False, None

    source_ids = {id(segment) for segment in candidate.source_segments}
    current = [segment for segment in context.pcb_data.segments
               if segment.net_id == candidate.source_segments[0].net_id]
    outside = [segment for segment in current if id(segment) not in source_ids]
    boundary = []
    outside_points = {
        (round(point[0], 7), round(point[1], 7))
        for segment in outside
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y))}
    for segment in candidate.source_segments:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            if (round(point[0], 7), round(point[1], 7)) in outside_points:
                boundary.append(point)
    candidate_points = {
        (round(point[0], 7), round(point[1], 7))
        for segment in candidate.segments
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y))}
    for segment in candidate.source_segments:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            if (round(point[0], 7), round(point[1], 7)) in candidate_points:
                boundary.append(point)
    from .algorithm import _connectivity_worse, _touches_other_same_net
    vias = [via for via in context.pcb_data.vias
            if via.net_id == candidate.source_segments[0].net_id]
    if _touches_other_same_net(candidate.segments, outside, vias, boundary):
        return False, None

    trial = outside + list(candidate.segments)
    net_id = candidate.source_segments[0].net_id
    after_grade = check_net_connectivity(
        net_id, trial, vias, context.pcb_data.pads_by_net.get(net_id, []), [],
        pcb_data=context.pcb_data)
    return not _connectivity_worse(before_grade, after_grade), after_grade


def _centering_proposals(pcb_data, doors, *, build_new_segments,
                         build_multi_door_path):
    """Yield candidates in M01 priority order: most doors first."""
    ranked = sorted(doors, key=lambda door: abs(door.offset), reverse=True)
    if build_multi_door_path:
        for branch_doors in _branch_door_groups(pcb_data, ranked):
            for directions in _ranked_direction_maps(
                    branch_doors, build_new_segments):
                yield branch_doors, center_across_branch_doors(
                    pcb_data, branch_doors,
                    build_new_segments=build_new_segments,
                    crossing_directions=directions)
        by_segment = {}
        for door in ranked:
            by_segment.setdefault(id(door.segment), []).append(door)
        groups = [tuple(group) for group in by_segment.values()
                  if len(group) >= 2]
        groups.sort(key=lambda group: (
            len(group), sum(abs(door.offset) for door in group)), reverse=True)
        for group in groups:
            yield group, center_across_multiple_doors(
                pcb_data, group, build_new_segments=build_new_segments)
    for door in ranked:
        yield (door,), center_with_sliding_neighbors(
            pcb_data, door, build_new_segments=build_new_segments)


def center_interpad_routes(context, results, deadline=None, *, net_ids,
                           proximity_mm=1.0,
                           build_new_segments=False,
                           build_multi_door_path=False):
    """G3.6: center editable octolinear branches across valid pad doors.

    Detection and exact clearance use KRT's existing spatial and geometry
    primitives.  Door coverage has priority over copper length and segment
    count.  Every accepted replacement preserves connectivity and the common
    immutable/branch scope; final G5 certification remains authoritative.
    """
    started = perf_counter()
    changes = GlossChanges()
    input_strips = []
    added_segments = []
    changed_net_ids = set()
    processed_doors = set()
    candidates_tested = 0
    length_delta = 0.0
    branches_centered = 0

    for net_id in net_ids:
        while deadline is None or perf_counter() < deadline:
            scan = find_interpad_doors(
                context.pcb_data, context.config, net_id=net_id,
                proximity_mm=proximity_mm, deadline=deadline,
                allowed_segment_ids=context.editable_segment_ids)
            doors = [door for door in scan.doors
                     if _door_key(door) not in processed_doors]
            if not doors:
                break
            current = [segment for segment in context.pcb_data.segments
                       if segment.net_id == net_id]
            vias = [via for via in context.pcb_data.vias
                    if via.net_id == net_id]
            before_grade = check_net_connectivity(
                net_id, current, vias,
                context.pcb_data.pads_by_net.get(net_id, []), [],
                pcb_data=context.pcb_data)
            accepted = None
            for selected_doors, candidate in _centering_proposals(
                    context.pcb_data, doors,
                    build_new_segments=build_new_segments,
                    build_multi_door_path=build_multi_door_path):
                if deadline is not None and perf_counter() >= deadline:
                    break
                if candidate is None:
                    continue
                candidates_tested += 1
                valid, _after_grade = _candidate_is_valid(
                    context, candidate, before_grade)
                if valid:
                    accepted = selected_doors, candidate
                    break
            if accepted is None:
                processed_doors.update(_door_key(door) for door in doors)
                break

            selected_doors, candidate = accepted
            removed = list(candidate.source_segments)
            removed_ids = {id(segment) for segment in removed}
            built = list(candidate.segments)
            branch_ids = _connected_segment_ids(
                context.pcb_data, candidate.source_segments)
            processed_doors.update(
                _door_key(door) for door in doors
                if id(door.segment) in branch_ids)

            # Segments created earlier in this same G3.6 call are held locally
            # until the stage emits its result.  Do not strip them from the
            # native board, and do not emit obsolete intermediate geometry.
            local_ids = {id(segment) for segment in added_segments}
            added_segments[:] = [segment for segment in added_segments
                                  if id(segment) not in removed_ids]
            external_removed = [segment for segment in removed
                                if id(segment) not in local_ids]
            native, _native_vias = release_result_custody(
                results, external_removed)
            input_strips.extend(native)
            context.pcb_data.segments = [
                segment for segment in context.pcb_data.segments
                if id(segment) not in removed_ids] + built
            context.replace_editable_segments(removed, built)
            if hasattr(context.pcb_data, "_foreign_seg_arr_cache"):
                context.pcb_data._foreign_seg_arr_cache = None
            changes.segments.extend(
                {"old": segment, "stage": "G3.6"} for segment in removed)
            changes.segments.extend(
                {"new": segment, "stage": "G3.6"} for segment in built)
            changes.doors.extend(selected_doors)
            added_segments.extend(built)
            length_delta += candidate.after_length - candidate.before_length
            branches_centered += 1
            changed_net_ids.add(net_id)
            context.refresh_net_obstacles(net_id)

    stats = {
        "branches_centered": branches_centered,
        "doors_centered": len(changes.doors),
        "segments_added": len(added_segments),
        "length_delta_mm": round(length_delta, 4),
        "net_ids_changed": changed_net_ids,
        "algorithm_ms": round((perf_counter() - started) * 1000.0, 3),
        "candidates_tested": candidates_tested,
    }
    return input_strips, added_segments, changes, stats
