"""G3.6 prototype: detect a single track crossing a two-pad gate.

KRT owns pad geometry, copper-layer expansion and the spatial index.  This
module only combines those existing operations; it does not implement a new
Rust primitive and it never mutates the board.
"""

from dataclasses import dataclass
import math
from time import perf_counter

from check_drc import SpatialIndex, pad_copper_layers, point_to_pad_distance
from kicad_parser import Segment


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


def center_with_sliding_neighbors(pcb_data, door):
    """Center one segment by sliding its ends on its two neighbours.

    This is the smallest complete M01 construction.  It is deliberately
    conservative: the crossed segment and both neighbours must form one
    simple, same-layer octolinear chain.  The returned objects are new KRT
    ``Segment`` instances; the PCBData is never mutated.
    """
    source = door.segment
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

    at_a, at_b = neighbours(a), neighbours(b)
    if len(at_a) != 1 or len(at_b) != 1 or at_a[0] is at_b[0]:
        return None
    first, last = at_a[0], at_b[0]
    outer_a, outer_b = _other_end(first, a), _other_end(last, b)
    rail_a = (a[0] - outer_a[0], a[1] - outer_a[1])
    rail_b = (b[0] - outer_b[0], b[1] - outer_b[1])
    if math.hypot(*rail_a) <= 1e-9 or math.hypot(*rail_b) <= 1e-9 or \
            not (_octolinear(outer_a, a) and _octolinear(outer_b, b)):
        return None

    # The new source line is parallel to the old one and passes through the
    # weighted door axis.  Its intersections with the two unchanged neighbour
    # lines are the new sliding joints.
    def line_intersection(point_a, vector_a, point_b, vector_b):
        denominator = _cross(vector_a, vector_b)
        if abs(denominator) <= 1e-9:
            return None
        delta = (point_b[0] - point_a[0], point_b[1] - point_a[1])
        scale = _cross(delta, vector_b) / denominator
        return (point_a[0] + scale * vector_a[0],
                point_a[1] + scale * vector_a[1])

    new_a = line_intersection(door.axis, direction, outer_a, rail_a)
    new_b = line_intersection(door.axis, direction, outer_b, rail_b)
    if new_a is None or new_b is None:
        return None
    translation = (door.axis[0] - door.crossing[0],
                   door.axis[1] - door.crossing[1])
    if ((new_b[0] - new_a[0]) * direction[0] +
            (new_b[1] - new_a[1]) * direction[1] <= 1e-9):
        return None

    # A rail may disappear at its outer anchor, but it may not reverse past it.
    for outer, old, new in ((outer_a, a, new_a), (outer_b, b, new_b)):
        old_vector = (old[0] - outer[0], old[1] - outer[1])
        new_vector = (new[0] - outer[0], new[1] - outer[1])
        if old_vector[0] * new_vector[0] + old_vector[1] * new_vector[1] < -1e-8:
            return None

    def make(start, end, template):
        if math.dist(start, end) <= 1e-7:
            return None
        return Segment(start[0], start[1], end[0], end[1], template.width,
                       template.layer, template.net_id)

    built = [make(outer_a, new_a, first),
             make(new_a, new_b, source),
             make(new_b, outer_b, last)]
    built = tuple(segment for segment in built if segment is not None)
    if not built or not all(_octolinear(
            (segment.start_x, segment.start_y),
            (segment.end_x, segment.end_y)) for segment in built):
        return None

    from net_queries import calculate_route_length
    old = (first, source, last)
    return InterpadCandidate(
        old, built, translation, calculate_route_length(old),
        calculate_route_length(built))


def find_interpad_doors(pcb_data, config, *, net_id=None,
                        max_pad_distance=5.0):
    """Find simple two-pad gates crossed by exactly one track segment.

    The measured interval is the space between the real KRT pad boundaries.
    Its axis is the midpoint after applying the clearance independently on
    each side.  A gate is returned only when the sole crossing segment still
    fits at its current width.  The function is read-only.
    """
    started = perf_counter()
    copper_layers = list(pcb_data.board_info.copper_layers or config.layers)
    index = SpatialIndex(cell_size=max_pad_distance)
    segments = [segment for segment in pcb_data.segments
                if not getattr(segment, "graphic", False)]
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
    seeds = segments if net_id is None else [segment for segment in segments
                                             if segment.net_id == net_id]
    for seed in seeds:
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
        ca = (pad_a.global_x, pad_a.global_y)
        cb = (pad_b.global_x, pad_b.global_y)
        centre_distance = math.dist(ca, cb)
        if centre_distance <= 1e-9 or centre_distance > max_pad_distance:
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
        unique_crossings += 1
        clearance_a = _pair_clearance(config, segment.net_id, pad_a, layer)
        clearance_b = _pair_clearance(config, segment.net_id, pad_b, layer)
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
            clearance_a, clearance_b, copper_gap, admissible_width,
            offset))

    elapsed_ms = (perf_counter() - started) * 1000.0
    return InterpadScan(tuple(doors), elapsed_ms, pad_pairs,
                        geometric_gates, unique_crossings)
