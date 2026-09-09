"""Build centered passages with regulatory clearance on their approaches.

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
    from .interpad import _intersection

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
            required = clearance
            previous = protected.get(id(pad), (pad, 0.))
            protected[id(pad)] = (pad, max(previous[1], required))
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
    from .support_prototype import build_candidate
    audit = []
    candidate = build_candidate(context, doors, deadline, audit=audit)
    for record in audit:
        if record.get('rejected'):
            print('Centering supports prototype rejected: ' + record['rejected'])
    return candidate


def certify_passages(candidate, doors):
    """Check the centered crossing and regulatory approach clearances."""
    from dataclasses import replace
    if candidate.passage_segments:
        candidate = replace(candidate, segments=candidate.passage_segments)
    constraints = passage_constraints(candidate, doors)
    return constraints is not None and respects_passages(candidate.segments, constraints)
