"""Shorten centered paths without spending their acquired pad clearance.

This is part of Centering candidate construction, before its KRT validation.
No board rules or copper are mutated by the search.
"""

import math
from time import perf_counter

from dgloss.krt_api import Segment
from dgloss.krt_api import calculate_route_length

# KRT's rounded-pad distance primitives use numerical approximations.
DISTANCE_TOLERANCE = 2e-4


def passage_constraints(candidate, doors):
    from .interpad import _axis_to_pad_distance, _intersection

    passages, protected = [], {}
    for door in doors:
        hits = []
        for segment in candidate.segments:
            start = (segment.start_x, segment.start_y)
            end = (segment.end_x, segment.end_y)
            if _intersection(start, end, door.edge_a, door.edge_b):
                length = math.dist(start, end)
                direction = ((end[0] - start[0]) / length,
                             (end[1] - start[1]) / length)
                hits.append(direction)
        if len(hits) != 1:
            return None
        direction = hits[0]
        passages.append((door, direction))
        for pad, clearance in ((door.pad_a, door.clearance_a),
                               (door.pad_b, door.clearance_b)):
            if pad.net_id == door.segment.net_id:
                continue
            required = max(clearance, _axis_to_pad_distance(
                door.axis, direction, pad) - door.segment.width / 2)
            previous = protected.get(id(pad), (pad, math.inf))
            protected[id(pad)] = (pad, min(previous[1], required))
    return passages, tuple(protected.values())


def respects_passages(segments, constraints):
    from .interpad import _cross, _intersection, _segment_pad_distance

    passages, protected = constraints
    for segment in segments:
        start = (segment.start_x, segment.start_y)
        end = (segment.end_x, segment.end_y)
        for pad, required in protected:
            if _segment_pad_distance(start, end, pad) - segment.width / 2 < \
                    required - DISTANCE_TOLERANCE:
                return False
    for door, direction in passages:
        hits = []
        for segment in segments:
            start = (segment.start_x, segment.start_y)
            end = (segment.end_x, segment.end_y)
            hit = _intersection(start, end, door.edge_a, door.edge_b,
                                allow_ab_ends=True)
            if hit is not None:
                vector = (end[0] - start[0], end[1] - start[1])
                if math.dist(hit[0], door.axis) > 1e-7 or \
                        abs(_cross(vector, direction)) > 1e-7:
                    return False
                hits.append(hit)
        if not hits:
            return False
    return True


def build_protected_path(context, doors, deadline=None):
    """Jointly choose local passages and short octolinear connections.

    Each stage is a finite centered segment. Dynamic programming chooses
    its length and the connections, without intersecting infinite axes.
    Shared pads receive the minimum acquired distance, checked on every edge.
    """
    from .algorithm import _candidate_segments, _simple_chains
    from .interpad import (InterpadCandidate, _axis_to_pad_distance,
                           _segment_pad_distance, door_crossing_options)

    if len(doors) < 2:
        return None
    net_id = doors[0].segment.net_id
    source_ids = {id(d.segment) for d in doors}
    chain = next((c for c in _simple_chains(context.pcb_data, net_id)
                  if source_ids <= {id(s) for s in c.segments}), None)
    if chain is None or not context.segments_editable(chain.segments):
        return None
    if chain.points[0] > chain.points[-1]:
        chain.points.reverse()
        chain.segments.reverse()
    positions = {id(s): i for i, s in enumerate(chain.segments)}
    ordered = sorted(doors, key=lambda d: (
        positions[id(d.segment)],
        math.dist(chain.points[positions[id(d.segment)]], d.crossing)))
    options = []
    for door in ordered:
        i = positions[id(door.segment)]
        a, b = chain.points[i:i + 2]
        forward = (b[0] - a[0], b[1] - a[1])
        options.append(tuple(
            v if sum(v[k] * forward[k] for k in (0, 1)) >= 0 else (-v[0], -v[1])
            for v in door_crossing_options(door, allow_reorientation=True)))
    template = chain.segments[0]

    def segment(a, b):
        return Segment(*a, *b, template.width, template.layer, net_id)

    if deadline is not None and perf_counter() >= deadline:
        return None
    # Resolve local directions once. The path search below is a layered DAG,
    # not an enumeration of joint orientation combinations.
    directions = [values[0] for values in options]
    best = None
    protected = {}
    for door, direction in zip(ordered, directions):
        for pad, rule in ((door.pad_a, door.clearance_a),
                          (door.pad_b, door.clearance_b)):
            if pad.net_id == net_id:
                continue
            required = max(rule, _axis_to_pad_distance(
                door.axis, direction, pad) - template.width / 2)
            protected[id(pad)] = (pad, min(
                protected.get(id(pad), (pad, math.inf))[1], required))
    protected = tuple(protected.values())

    def safe(segments):
        return all(math.hypot(s.end_x - s.start_x, s.end_y - s.start_y)
                   >= context.coord.grid_step - 1e-9 for s in segments) and \
            all(_segment_pad_distance(
            (s.start_x, s.start_y), (s.end_x, s.end_y), pad) - s.width / 2
            >= required - DISTANCE_TOLERANCE
            for s in segments for pad, required in protected) and \
            context.clearance_adapter.connector_clears(segments)

    def connections(start, end):
        if math.dist(start, end) <= 1e-9:
            yield []
            return
        for proposed in _candidate_segments(start, end, template.layer,
                                            template.width, net_id):
            if math.dist(start, (proposed[0].start_x, proposed[0].start_y)) > 1e-7 or \
                    math.dist(end, (proposed[-1].end_x, proposed[-1].end_y)) > 1e-7:
                continue
            if any(math.dist((a.end_x, a.end_y), (b.start_x, b.start_y)) > 1e-7
                   for a, b in zip(proposed, proposed[1:])):
                continue
            yield proposed

    if any(_segment_pad_distance(d.axis, d.axis, pad) - template.width / 2
           < required - DISTANCE_TOLERANCE
           for d in ordered for pad, required in protected):
        return None
    states = [(0.0, chain.points[0], [])]
    for door, direction in zip(ordered, directions):
        next_states = []
        for half_length in (context.coord.grid_step, 0.5, 1.0, 2.0, 4.0, 8.0):
            if deadline is not None and perf_counter() >= deadline:
                return best
            entry = tuple(door.axis[k] - direction[k] * half_length for k in (0, 1))
            exit_point = tuple(door.axis[k] + direction[k] * half_length for k in (0, 1))
            passage = segment(entry, exit_point)
            if not safe([passage]):
                continue
            choices = []
            for cost, start, previous in states:
                for connector in connections(start, entry):
                    if safe(connector):
                        built = list(connector) + [passage]
                        choices.append((cost + calculate_route_length(built),
                                        exit_point, previous + built))
            if choices:
                next_states.append(min(choices, key=lambda v: v[0]))
        states = next_states
        if not states:
            break
    constraints = (tuple(zip(ordered, directions)), protected)
    for cost, start, previous in states:
        for connector in connections(start, chain.points[-1]):
            built = previous + list(connector)
            if not safe(connector) or not respects_passages(built, constraints):
                continue
            length = calculate_route_length(built)
            if best is None or length < best.after_length:
                best = InterpadCandidate(tuple(chain.segments), tuple(built),
                    (0.0, 0.0), calculate_route_length(chain.segments), length)
    return best


def certify_passages(candidate, doors):
    """Check acquired obstacle distances on the whole proposed replacement."""
    constraints = passage_constraints(candidate, doors)
    return constraints is not None and respects_passages(candidate.segments, constraints)
