"""Same-net chain construction shared by route and via searches."""

from collections import defaultdict
from dataclasses import dataclass
import math
from .krt_api import pos_key, point_to_pad_distance, FP_EPS_MM
from .board_views import board_views


@dataclass
class _Chain:
    segments: list
    points: list
    layer: str
    width: float


def _simple_chains(pcb_data, net_id, allowed_segment_ids=None):
    """Return conservative same-layer/width chains; pads, vias and nodes anchor."""
    views = board_views(pcb_data)
    all_segments = views.segments(net_id)
    net_vias = views.vias(net_id)
    net_segments = [s for s in all_segments if
                    not getattr(s, "graphic", False) and
                    not getattr(s, "locked", False) and
                    (allowed_segment_ids is None or
                     id(s) in allowed_segment_ids)]
    if len(net_segments) < 2:
        return []
    key = (tuple(map(id, all_segments)), tuple(map(id, net_segments)),
           tuple(map(id, net_vias)))
    cached = views.chains.get(net_id)
    if cached is not None and cached[0] == key:
        return cached[1]

    incidence = defaultdict(int)
    for seg in all_segments:
        incidence[pos_key(seg.start_x, seg.start_y)] += 1
        incidence[pos_key(seg.end_x, seg.end_y)] += 1
    via_points = {pos_key(v.x, v.y) for v in net_vias}

    groups = defaultdict(list)
    for seg in net_segments:
        groups[(seg.layer, seg.width)].append(seg)

    chains = []
    for (layer, width), segments in sorted(groups.items()):
        adjacency = defaultdict(list)
        actual = {}
        for seg in segments:
            a = pos_key(seg.start_x, seg.start_y)
            b = pos_key(seg.end_x, seg.end_y)
            adjacency[a].append(seg)
            adjacency[b].append(seg)
            actual[(id(seg), a)] = (seg.start_x, seg.start_y)
            actual[(id(seg), b)] = (seg.end_x, seg.end_y)

        def interior(key):
            point = actual.get((id(adjacency[key][0]), key), key)
            return (len(adjacency[key]) == 2 and incidence[key] == 2 and
                    math.dist(actual[(id(adjacency[key][1]), key)], point) <= FP_EPS_MM and
                    key not in via_points and
                    not views.pad_holds(net_id, point, layer, width / 2))

        anchors = sorted(key for key in adjacency if not interior(key))
        used = set()
        for anchor in anchors:
            for first in adjacency[anchor]:
                if id(first) in used:
                    continue
                ordered = []
                points = [actual[(id(first), anchor)]]
                current = anchor
                seg = first
                while True:
                    used.add(id(seg))
                    ordered.append(seg)
                    a = pos_key(seg.start_x, seg.start_y)
                    b = pos_key(seg.end_x, seg.end_y)
                    other = b if a == current else a
                    points.append(actual[(id(seg), other)])
                    current = other
                    if current == anchor or not interior(current):
                        break
                    following = [candidate for candidate in adjacency[current]
                                 if id(candidate) not in used]
                    if not following:
                        break
                    seg = following[0]
                if current != anchor and len(ordered) >= 2:
                    chains.append(_Chain(ordered, points, layer, width))
    views.chains[net_id] = key, chains, tuple(all_segments), tuple(net_vias)
    return chains


def _pad_on_layer(pad, layer):
    return layer in (pad.layers or []) or "*.Cu" in (pad.layers or [])

def _walk_branch_chain(pcb_data, net_id, node, branch):
    """Walk from a T along its simple branch to the next KRT anchor."""
    net_segments = [segment for segment in pcb_data.segments
                    if segment.net_id == net_id and
                    not getattr(segment, "graphic", False)]
    group = [segment for segment in net_segments
             if segment.layer == branch.layer and
             segment.width == branch.width and
             not getattr(segment, "locked", False)]
    adjacency = defaultdict(list)
    actual = {}
    incidence = defaultdict(int)
    for segment in net_segments:
        incidence[pos_key(segment.start_x, segment.start_y)] += 1
        incidence[pos_key(segment.end_x, segment.end_y)] += 1
    for segment in group:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            key = pos_key(*point)
            adjacency[key].append(segment)
            actual[(id(segment), key)] = point
    via_keys = {pos_key(via.x, via.y) for via in pcb_data.vias
                if via.net_id == net_id}
    pads = pcb_data.pads_by_net.get(net_id, [])

    chain = []
    current = pos_key(*node)
    segment = branch
    used = set()
    anchor = node
    while True:
        used.add(id(segment))
        chain.append(segment)
        a = pos_key(segment.start_x, segment.start_y)
        b = pos_key(segment.end_x, segment.end_y)
        other = b if a == current else a
        anchor = actual[(id(segment), other)]
        current = other
        anchored = (incidence[current] != 2 or current in via_keys or
                    any(_pad_on_layer(pad, branch.layer) and
                        point_to_pad_distance(anchor[0], anchor[1], pad) <=
                        branch.width / 2.0 + 1e-6 for pad in pads))
        if anchored:
            break
        following = [candidate for candidate in adjacency[current]
                     if id(candidate) not in used]
        if len(following) != 1:
            break
        if math.dist(actual[(id(following[0]), current)], anchor) > FP_EPS_MM:
            break  # Rounded adjacency must not invent an actual shared vertex.
        segment = following[0]
    return chain, anchor
