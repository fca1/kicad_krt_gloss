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


def _intersection(a, b, c, d, eps=1e-9):
    """Return (point, parameter on AB, parameter on CD), or ``None``."""
    abx, aby = b[0] - a[0], b[1] - a[1]
    cdx, cdy = d[0] - c[0], d[1] - c[1]
    denominator = abx * cdy - aby * cdx
    if abs(denominator) <= eps:
        return None
    acx, acy = c[0] - a[0], c[1] - a[1]
    t = (acx * cdy - acy * cdx) / denominator
    u = (acx * aby - acy * abx) / denominator
    if eps < t < 1.0 - eps and eps < u < 1.0 - eps:
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
                (segment.end_x, segment.end_y), edge_a, edge_b)
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
