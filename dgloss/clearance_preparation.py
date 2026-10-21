"""Prepared immutable geometry and physical broad-phase filters for Gloss.

Integrated from the validated performance prototype. KRT predicates remain
unchanged; pads/rules are fixed per run, copper arrays follow list revisions.
"""
import math
import numpy as np
from . import krt_clearance as clearance, krt_sweep as sweep


# Outside this range, rounding can consume KRT's nanometre comparison epsilon.
# This only disables the broad phase; the original exact calculation remains.
FILTER_COORD_LIMIT = clearance.FP_EPS_MM / (32 * np.finfo(float).eps)


def candidate_bounds(x1, y1, x2, y2, reach):
    values = (x1, y1, x2, y2, reach)
    if reach < 0 or not all(math.isfinite(v) and abs(v) <= FILTER_COORD_LIMIT
                            for v in values):
        return None
    margin = math.nextafter(reach + clearance.FP_EPS_MM, math.inf)
    return (math.nextafter(min(x1, x2)-margin, -math.inf),
            math.nextafter(min(y1, y2)-margin, -math.inf),
            math.nextafter(max(x1, x2)+margin, math.inf),
            math.nextafter(max(y1, y2)+margin, math.inf))


def polygon_bounds(polygons):
    """Enclose every component; malformed/extreme outlines use the exact path."""
    try:
        points = [point for ring in polygons for point in ring]
        if not points or any(not ring for ring in polygons):
            return None
        if any(len(point) != 2 or not all(
                math.isfinite(v) and abs(v) <= FILTER_COORD_LIMIT for v in point)
                for point in points):
            return None
        xs, ys = zip(*points)
        return (math.nextafter(min(xs), -math.inf),
                math.nextafter(min(ys), -math.inf),
                math.nextafter(max(xs), math.inf),
                math.nextafter(max(ys), math.inf))
    except (TypeError, ValueError, OverflowError):
        return None


def prepared_holes(self):
    """KRT's fixed drill capsules, retained for this adapter's single action."""
    if '_fixed_holes' not in self.__dict__:
        arrays = clearance._foreign_hole_capsules(self.pcb)
        _nid, ax, ay, bx, by, radius, local = arrays
        valid = np.ones(len(ax), dtype=bool)
        for values in (ax, ay, bx, by, radius, local):
            valid &= np.isfinite(values) & (np.abs(values) <= FILTER_COORD_LIMIT)
        valid &= radius >= 0
        with np.errstate(over='ignore', invalid='ignore'):
            bounds = (np.nextafter(np.minimum(ax, bx)-radius, -np.inf),
                      np.nextafter(np.minimum(ay, by)-radius, -np.inf),
                      np.nextafter(np.maximum(ax, bx)+radius, np.inf),
                      np.nextafter(np.maximum(ay, by)+radius, np.inf))
        self._fixed_holes = arrays, bounds, valid
    return self._fixed_holes


def early_segment(self, seg):
    effective = self._effective_clearance(seg.net_id, seg.layer)
    required = effective + seg.width / 2 - clearance.FP_EPS_MM
    if not self._pad_distance(seg.net_id, seg.start_x, seg.start_y,
            seg.end_x, seg.end_y, seg.layer, effective, seg.width / 2) >= required:
        return False
    if not clearance._exact_foreign_segment_distance(
            self.pcb, seg.net_id, seg.start_x, seg.start_y, seg.end_x, seg.end_y,
            seg.layer, net_clearances=self.net_clearances, base_clearance=effective,
            track_clearances=self.track_clearances,
            prepared_copper=self._prepared_copper(seg.layer), half_width=seg.width/2) >= required:
        return False
    if not clearance._exact_foreign_hole_distance(self.pcb, seg.net_id,
            seg.start_x, seg.start_y, seg.end_x, seg.end_y, self.npth_clearance,
            prepared_holes=self._prepared_holes(), half_width=seg.width/2
            ) >= self.npth_clearance + seg.width / 2 - clearance.FP_EPS_MM:
        return False
    return self._edge_clears(seg) and self._keepouts_clear(seg)


def prepared_pad_distance(self, net_id, x1, y1, x2, y2, layer, effective, half_width):
    cache = self.__dict__.setdefault('_perf_fixed_pads', {})
    if layer not in cache:
        arrays = sweep._foreign_pad_arrays(self.pcb, layer)
        nid, cx, cy, hx, hy, radius, c, s, ex, ey, local, custom = arrays
        ix, iy = hx-radius, hy-radius
        corners_x = np.asarray([-ix, ix, ix, -ix])
        corners_y = np.asarray([-iy, -iy, iy, iy])
        ax = cx + corners_x*c - corners_y*s
        ay = cy + corners_x*s + corners_y*c
        cache[layer] = arrays, (ix, iy, ax, ay, np.roll(ax, -1, axis=0),
                               np.roll(ay, -1, axis=0)), {}, [
            (foreign_net, pad, polygon_bounds(pad.polygons))
            for foreign_net, pad in custom]
    arrays, geometry, rule_cache, custom_bounds = cache[layer]
    nid, cx, cy, hx, hy, radius, c, s, ex, ey, local, custom = arrays
    if effective not in rule_cache:
        rules = np.maximum(effective, local)
        if self.net_clearances:
            rules = np.maximum(rules, [self.net_clearances.get(int(n), effective) for n in nid])
        rule_cache[effective] = rules
    rules = rule_cache[effective]
    reach = rules + half_width
    near = ((nid != net_id) & (cx+ex >= min(x1, x2)-reach) &
            (cx-ex <= max(x1, x2)+reach) & (cy+ey >= min(y1, y2)-reach) &
            (cy-ey <= max(y1, y2)+reach))
    best = float('inf')
    if near.any():
        ix, iy, ax, ay, bx, by = geometry
        distance = np.min(sweep._seg_capsule_axis_dist(
            x1, y1, x2, y2, ax[:, near], ay[:, near], bx[:, near], by[:, near]), axis=0)
        for x, y in ((x1, y1), (x2, y2)):
            lx = (x-cx[near])*c[near]+(y-cy[near])*s[near]
            ly = -(x-cx[near])*s[near]+(y-cy[near])*c[near]
            distance = np.where((np.abs(lx) <= ix[near]) & (np.abs(ly) <= iy[near]), 0., distance)
        distance = np.maximum(0., distance-radius[near])
        best = float(np.min(distance-(rules[near]-effective)))
    for foreign_net, pad, bounds in custom_bounds:
        if foreign_net != net_id:
            rule = max(effective, getattr(pad, 'local_clearance', 0.) or 0.,
                       (self.net_clearances or {}).get(foreign_net, effective))
            query = candidate_bounds(x1, y1, x2, y2, rule+half_width) if bounds else None
            if query is not None and (bounds[2] < query[0] or bounds[0] > query[2]
                                      or bounds[3] < query[1] or bounds[1] > query[3]):
                continue
            best = min(best, sweep.polygon_axis_distance(x1, y1, x2, y2, pad.polygons)
                       -(rule-effective))
    return best


class BoardSubset:
    def __init__(self, pcb, **overrides):
        self._source = pcb
        self.__dict__.update(overrides)

    def __getattr__(self, name):
        return getattr(self._source, name)


def via_subset(adapter, old, new):
    """Keep all pads; only cull distant track/via copper and drill obstacles."""
    pcb = adapter.pcb
    cache = adapter.__dict__.setdefault('_perf_via_arrays', {})
    if cache.get('segments') is not pcb.segments:
        cache['segments'] = pcb.segments  # retain the revision's objects
        cache['bounds'] = np.asarray([
            (min(s.start_x, s.end_x)-s.width/2, min(s.start_y, s.end_y)-s.width/2,
             max(s.start_x, s.end_x)+s.width/2, max(s.start_y, s.end_y)+s.width/2)
            for s in pcb.segments]).reshape((-1, 4))
        cache['segment_rules'] = {}
    own = max(adapter.clearance, (adapter.net_clearances or {}).get(old.net_id, adapter.clearance))
    if own not in cache['segment_rules']:
        cache['segment_rules'][own] = np.asarray([
            adapter.config.stack_clearance(max(own, (adapter.net_clearances or {}).get(s.net_id, adapter.clearance)))
            for s in pcb.segments])
    x0, x1 = sorted((old.x, new.x))
    y0, y1 = sorted((old.y, new.y))
    bounds = cache['bounds']
    radius = cache['segment_rules'][own] + max(old.size, new.size)/2
    near = ((bounds[:, 2] >= np.nextafter(x0-radius, -np.inf)) &
            (bounds[:, 0] <= np.nextafter(x1+radius, np.inf)) &
            (bounds[:, 3] >= np.nextafter(y0-radius, -np.inf)) &
            (bounds[:, 1] <= np.nextafter(y1+radius, np.inf)))
    segments = [pcb.segments[i] for i in np.flatnonzero(near)]
    # Drill spacing applies even to same-net vias. Keep both physical envelopes.
    hole = getattr(adapter.config, 'hole_to_hole_clearance', None) or clearance.HOLE_TO_HOLE_CLEARANCE
    vias = []
    for via in pcb.vias:
        pair = adapter.config.stack_clearance(max(own, (adapter.net_clearances or {}).get(via.net_id, adapter.clearance)))
        reach = max(pair+(max(old.size, new.size)+via.size)/2,
                    hole+(max(old.drill, new.drill)+via.drill)/2)
        if (np.nextafter(x0-reach, -np.inf) <= via.x <= np.nextafter(x1+reach, np.inf) and
                np.nextafter(y0-reach, -np.inf) <= via.y <= np.nextafter(y1+reach, np.inf)):
            vias.append(via)
    return BoardSubset(pcb, segments=segments, vias=vias)
