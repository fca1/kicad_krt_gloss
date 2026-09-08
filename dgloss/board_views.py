"""Run-local net views and immutable pad queries backed by KRT's spatial index."""
from collections import defaultdict, OrderedDict

from .krt_api import SpatialIndex, point_to_pad_distance


class BoardViews:
    """Copper objects are replaced, never edited in place during an operation."""

    def __init__(self, pcb):
        self.pcb = pcb
        self.segment_source = self.via_source = None
        self.chains = {}
        self.pad_contacts = OrderedDict()
        self.pad_index = None

    def segments(self, net):
        if self.segment_source is not self.pcb.segments:
            self.segment_source = self.pcb.segments
            self.by_net = defaultdict(list)
            for segment in self.segment_source:
                self.by_net[segment.net_id].append(segment)
        return self.by_net.get(net, [])

    def vias(self, net):
        if self.via_source is not self.pcb.vias:
            self.via_source = self.pcb.vias
            self.vias_by_net = defaultdict(list)
            for via in self.via_source:
                self.vias_by_net[via.net_id].append(via)
        return self.vias_by_net.get(net, [])

    def pad_holds(self, net, point, layer, half_width):
        key = net, point, layer, half_width
        if key in self.pad_contacts:
            self.pad_contacts.move_to_end(key)
            return self.pad_contacts[key]
        if self.pad_index is None:
            self.pad_index = SpatialIndex(cell_size=max(1.0, max(
                (s.width / 2 + 1e-6 for s in self.pcb.segments), default=0.0)))
            # Keep the existing wildcard semantics; KRT supplies shape extents
            # and distances. A single query layer avoids imposing new rules.
            for pad_net, pads in self.pcb.pads_by_net.items():
                for pad in pads:
                    self.pad_index.add_pad(pad, pad_net, ['F.Cu'])
        # One neighboring cell covers the maximum half-width in this run.
        # F.Cu is an index bucket only; the actual layer is checked below.
        held = any(pad_net == net and
                   (layer in pad.layers or any('*' in name for name in pad.layers)) and
                   point_to_pad_distance(*point, pad) <= half_width + 1e-6
                   for pad, pad_net in self.pad_index.get_nearby_pads(*point, 'F.Cu'))
        self.pad_contacts[key] = held
        if len(self.pad_contacts) > 16384:
            self.pad_contacts.popitem(last=False)
        return held


def board_views(pcb):
    views = getattr(pcb, '_gloss_views', None)
    if views is None:
        views = pcb._gloss_views = BoardViews(pcb)
    return views
