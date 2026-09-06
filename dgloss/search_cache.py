"""Bounded failed-search certificates, invalidated by changed copper regions."""

from collections import OrderedDict
from math import hypot


def copper_box(item):
    if hasattr(item, "start_x"):
        radius = item.width / 2
        return (min(item.start_x, item.end_x) - radius,
                min(item.start_y, item.end_y) - radius,
                max(item.start_x, item.end_x) + radius,
                max(item.start_y, item.end_y) + radius)
    radius = item.size / 2
    return item.x - radius, item.y - radius, item.x + radius, item.y + radius


def overlaps(first, second):
    return not (first[2] < second[0] or second[2] < first[0] or
                first[3] < second[1] or second[3] < first[1])


class SearchCache:
    def __init__(self, pcb, config):
        self.pcb, self.config = pcb, config
        self.entries = OrderedDict()
        self.events = []
        self.stats = {"hits": 0, "misses": 0, "invalidations": 0}

    def changed(self, segments, vias=()):
        for item in list(segments) + list(vias):
            self.events.append((item.net_id, copper_box(item)))
        if len(self.events) > 4096:
            self.events.clear()
            self.entries.clear()

    def token(self, kind, net_id, source, policy):
        # Keep source objects alive in the entry, so ids cannot be recycled.
        key = kind, net_id, tuple(map(id, source)), policy
        found = self.entries.get(key)
        if found is not None:
            revision, boxes, _retained = found
            if not any(net == net_id or any(overlaps(box, area) for area in boxes)
                       for net, box in self.events[revision:]):
                self.stats["hits"] += 1
                self.entries.move_to_end(key)
                return key, True
            self.stats["invalidations"] += 1
            del self.entries[key]
        self.stats["misses"] += 1
        return key, False

    def remember_failure(self, key, source):
        if not source:
            return
        boxes = [copper_box(s) for s in source]
        # Slides can leave the original bounding box, but their displacement
        # is bounded by source length. Include KRT's broad-phase distance window.
        reach = sum(hypot(s.end_x - s.start_x, s.end_y - s.start_y) for s in source)
        rules = [5.0, self.config.clearance]
        for field in ("net_clearances", "track_clearances", "layer_clearances"):
            rules.extend((getattr(self.config, field, None) or {}).values())
        margin = reach + max(rules)
        area = (min(b[0] for b in boxes) - margin, min(b[1] for b in boxes) - margin,
                max(b[2] for b in boxes) + margin, max(b[3] for b in boxes) + margin)
        dependencies = [area]
        # A foreign change anywhere in an own-net pour may change the candidate's
        # electrical certificate, even when it is far from the searched track.
        for zone in getattr(self.pcb, "zones", ()) or ():
            if zone.net_id == key[1] and zone.polygon:
                xs, ys = zip(*zone.polygon)
                zone_margin = max(margin, (getattr(zone, "clearance", None) or 0) + 1)
                dependencies.append((min(xs) - zone_margin, min(ys) - zone_margin,
                                     max(xs) + zone_margin, max(ys) + zone_margin))
        self.entries[key] = len(self.events), dependencies, tuple(source)
        self.entries.move_to_end(key)
        while len(self.entries) > 2048:
            self.entries.popitem(last=False)
