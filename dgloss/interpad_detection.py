"""Discover two-pad gates with KRT broad phase and exact pad geometry."""

import math
from time import perf_counter
from .krt_api import Segment, SpatialIndex, pad_copper_layers
from .interpad_types import InterpadDoor, InterpadScan
from .interpad_geometry import _intersection, _edge_towards, _pair_clearance


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
