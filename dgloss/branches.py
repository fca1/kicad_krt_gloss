"""Elementary-branch discovery from selected KRT segment seeds."""

from collections import defaultdict

from check_drc import point_to_pad_distance
from connectivity import COINCIDENCE_TOL, via_copper_layers
from routing_utils import pos_key


def _pad_stops(pcb_data, net_id, point, layer, half_width):
    for pad in pcb_data.pads_by_net.get(net_id, ()):
        if layer not in pad.layers and not any("*" in name for name in pad.layers):
            continue
        if point_to_pad_distance(point[0], point[1], pad) <= \
                half_width + COINCIDENCE_TOL:
            return True
    return False


def elementary_branch_segment_ids(pcb_data, seed_segments):
    """Return the union of maximal unbranched paths containing the seeds.

    Width and layer changes remain inside a branch. A same-net via joins the
    layer-local endpoint graphs when exactly one continuation exists through
    it. Pads, free ends and junctions stop the walk.
    """
    seeds_by_net = defaultdict(list)
    current_ids = {id(segment) for segment in pcb_data.segments}
    for segment in seed_segments or ():
        if (id(segment) in current_ids and segment.net_id and
                not getattr(segment, "graphic", False)):
            seeds_by_net[segment.net_id].append(segment)

    selected = set()
    branch_count = 0
    for net_id, seeds in seeds_by_net.items():
        net_segments = [segment for segment in pcb_data.segments
                        if segment.net_id == net_id and
                        not getattr(segment, "graphic", False)]
        adjacency = defaultdict(list)
        actual = {}
        for segment in net_segments:
            for point in ((segment.start_x, segment.start_y),
                          (segment.end_x, segment.end_y)):
                node = (pos_key(*point), segment.layer)
                adjacency[node].append(segment)
                actual[(id(segment), node)] = point

        copper_layers = getattr(pcb_data.board_info, "copper_layers", None)
        vias_at_position = defaultdict(list)
        for via in pcb_data.vias:
            if via.net_id == net_id:
                vias_at_position[pos_key(via.x, via.y)].append(via)
        nodes_at_position = defaultdict(list)
        for node in adjacency:
            nodes_at_position[node[0]].append(node)

        def incident(node):
            reached_layers = {node[1]}
            for via in vias_at_position.get(node[0], ()):
                layers = via_copper_layers(via, copper_layers)
                if node[1] in layers:
                    reached_layers.update(layers)
            nodes = [candidate for candidate in nodes_at_position[node[0]]
                     if candidate[1] in reached_layers]
            unique = {}
            for linked in nodes:
                for segment in adjacency[linked]:
                    unique[id(segment)] = segment
            return list(unique.values())

        def walk(seed, start_node):
            found = {id(seed)}
            segment = seed
            node = start_node
            while True:
                point = actual[(id(segment), node)]
                if _pad_stops(
                        pcb_data, net_id, point, segment.layer,
                        segment.width / 2.0):
                    break
                linked = incident(node)
                if len(linked) != 2:
                    break
                following = next((item for item in linked
                                  if item is not segment), None)
                if following is None or id(following) in found:
                    break
                found.add(id(following))
                a = (pos_key(following.start_x, following.start_y),
                     following.layer)
                b = (pos_key(following.end_x, following.end_y),
                     following.layer)
                if following.layer != node[1]:
                    node = b if a[0] == node[0] else a
                else:
                    node = b if a == node else a
                segment = following
            return found

        seen_seeds = set()
        for seed in seeds:
            if id(seed) in seen_seeds:
                continue
            a = (pos_key(seed.start_x, seed.start_y), seed.layer)
            b = (pos_key(seed.end_x, seed.end_y), seed.layer)
            branch = walk(seed, a) | walk(seed, b)
            selected.update(branch)
            seen_seeds.update(branch)
            branch_count += 1
    return selected, branch_count
