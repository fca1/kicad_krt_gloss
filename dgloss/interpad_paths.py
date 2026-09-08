"""Construct candidate paths through already identified centering gates."""

import math
from .krt_api import Segment
from .interpad_types import InterpadCandidate
from .interpad_geometry import _cross, _other_end, _octolinear, door_crossing_direction, _line_intersection, _native_pad_at


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
            from dgloss.krt_api import calculate_route_length
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

    from dgloss.krt_api import calculate_route_length
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
    from dgloss.krt_api import calculate_route_length
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
    from dgloss.krt_api import calculate_route_length
    first_door = ordered_doors[0]
    translation = (first_door.axis[0] - first_door.crossing[0],
                   first_door.axis[1] - first_door.crossing[1])
    return InterpadCandidate(
        tuple(chain), built, translation, calculate_route_length(chain),
        calculate_route_length(built))
