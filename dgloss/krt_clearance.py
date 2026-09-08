"""G3 clearance adapter: KRT owns every geometry and rule calculation."""

from functools import lru_cache
from functools import wraps
from contextlib import contextmanager, nullcontext

import numpy as np

from dgloss.krt_api import (board_edge_geometry, check_pad_drill_via_overlap,
                       check_pad_via_overlap, check_via_board_edge,
                       check_via_drill_overlap,
                       check_via_board_edge_poly, check_via_segment_overlap,
                       check_via_via_overlap, pad_copper_layers,
                       pads_shared_layer_clearance, _point_on_board,
                       _segment_to_rings_distance)
from dgloss.krt_api import point_in_polygon, point_to_polygon_edge_distance
from dgloss.krt_api import (Segment, FP_EPS_MM, check_segment_overlap,
                           pad_drill_capsule)
from .krt_sweep import foreign_pad_clearance_distance, pad_axis_distance
from dgloss.krt_api import HOLE_TO_HOLE_CLEARANCE, NPTH_TO_TRACK_CLEARANCE
from dgloss.krt_api import (_foreign_seg_arrays, _foreign_hole_capsules,
                           _seg_capsule_axis_dist)


def _exact_foreign_segment_distance(pcb_data, net_id, x1, y1, x2, y2,
                                    layer, *, net_clearances=None,
                                    base_clearance=0.0,
                                    track_clearances=None, prepared_copper=None,
                                    half_width=None):
    """Compose KRT's cached arrays and exact vectorized capsule distance.

    KRT owns the obstacle arrays, broad phase and analytic distance primitive.
    dgloss only folds KRT's rule excess into the returned distance, exactly as
    KRT's sampled convenience helper does.
    """
    arrays, bounds = (prepared_copper if prepared_copper is not None else
                      (_foreign_seg_arrays(pcb_data, layer), None))
    nid, fax, fay, fbx, fby, foreign_half_width = arrays
    if nid.size == 0:
        return 1e9

    min_x, max_x, min_y, max_y = (bounds if bounds is not None else (
        np.minimum(fax, fbx) - foreign_half_width, np.maximum(fax, fbx) + foreign_half_width,
        np.minimum(fay, fby) - foreign_half_width, np.maximum(fay, fby) + foreign_half_width))
    net_rules, track_rules = net_clearances or {}, track_clearances or {}
    near = nid != net_id
    if half_width is not None:
        radius = half_width + max(base_clearance, max(net_rules.values(), default=0.),
                                  max(track_rules.values(), default=0.))
        near &= ((max_x >= min(x1, x2) - radius) &
                 (min_x <= max(x1, x2) + radius) &
                 (max_y >= min(y1, y2) - radius) &
                 (min_y <= max(y1, y2) + radius))
    if not near.any():
        return 1e9

    distance = (_seg_capsule_axis_dist(
        x1, y1, x2, y2, fax[near], fay[near], fbx[near], fby[near]) -
        foreign_half_width[near])
    excess = np.asarray([max(0., net_rules.get(int(n), base_clearance)-base_clearance,
                             track_rules.get(int(n), 0.)-base_clearance) for n in nid[near]])
    return float(np.min(distance - excess))


def _exact_foreign_hole_distance(pcb, net_id, x1, y1, x2, y2, clearance):
    nid, ax, ay, bx, by, radius, local = _foreign_hole_capsules(pcb)
    mask = nid != net_id
    if not mask.any():
        return float('inf')
    distance = _seg_capsule_axis_dist(x1, y1, x2, y2, ax[mask], ay[mask], bx[mask], by[mask])
    return float(np.min(distance-radius[mask]-np.maximum(0., local[mask]-clearance)))


def stable_copper_search(function):
    """Batch read-only proposals; never decorate a function that commits copper."""
    @wraps(function)
    def wrapped(context, *args, **kwargs):
        batch = getattr(context.clearance_adapter, "stable_copper", nullcontext)
        with batch():
            return function(context, *args, **kwargs)
    return wrapped


class KrtClearanceAdapter:
    """Thin G3 adapter for the predicate embedded in KRT's final smooth.

    No clearance geometry is implemented by dgloss: distances, pad shapes,
    class/track rules, board geometry and keepout geometry all come from KRT.
    This class only composes those KRT results because the original
    ``smooth_octolinear_chains.clears`` predicate is a local closure and cannot
    be imported without modifying KRT.
    """

    def __init__(self, pcb_data, config):
        self.pcb = pcb_data
        self.config = config
        self.clearance = config.clearance
        self.net_clearances = getattr(config, "net_clearances", None) or None
        self.track_clearances = getattr(config, "track_clearances", None) or None
        self.npth_clearance = max(self.clearance, NPTH_TO_TRACK_CLEARANCE)
        self.edge_clearance = max(
            self.clearance, getattr(config, "board_edge_clearance", 0.0))
        self.edge_rings, self.edge_outer, self.edge_cutouts = \
            board_edge_geometry(pcb_data.board_info)
        self.board_bounds = pcb_data.board_info.board_bounds
        self.keepouts = self._collect_keepouts()
        self.via_keepouts = self._collect_keepouts(for_vias=True)
        # Pads and rules are immutable during this adapter's single Gloss run.
        # Never cache distances to tracks/vias: those move between candidates.
        # Keep coordinates exact (no grid rounding of a clearance certificate).
        self._pad_distance = lru_cache(maxsize=8192)(self._uncached_pad_distance)
        self._copper_batch = None
        self.copper_data_stats = {"builds": 0, "reuses": 0, "certificate_hits": 0}

    @contextmanager
    def stable_copper(self):
        """Reuse KRT arrays only while the caller guarantees no copper mutation.

        A scope ends before committing a candidate. No arrays escape that
        revision, even on rejection, timeout or an exception. Outside this
        scope KRT's regular signature/invalidation checks remain in charge.
        """
        previous = self._copper_batch
        if previous is None:
            self._copper_batch = {}
        try:
            yield
        finally:
            self._copper_batch = previous

    def _prepared_copper(self, layer):
        batch = getattr(self, "_copper_batch", None)
        if batch is None:
            return None
        if layer in batch:
            self.copper_data_stats["reuses"] += 1
            return batch[layer]
        arrays = _foreign_seg_arrays(self.pcb, layer)
        _nid, ax, ay, bx, by, half = arrays
        bounds = (np.minimum(ax, bx) - half, np.maximum(ax, bx) + half,
                  np.minimum(ay, by) - half, np.maximum(ay, by) + half)
        batch[layer] = arrays, bounds
        self.copper_data_stats["builds"] += 1
        return batch[layer]

    def _uncached_pad_distance(self, net_id, x1, y1, x2, y2, layer, effective, half_width):
        return foreign_pad_clearance_distance(
            self.pcb, net_id, x1, y1, x2, y2, layer, effective,
            self.net_clearances, half_width)

    def _collect_keepouts(self, for_vias=False):
        keepouts = []
        for area in getattr(self.pcb.board_info, "keepouts", None) or []:
            allowed_key = "vias_allowed" if for_vias else "tracks_allowed"
            if area.get(allowed_key, True):
                continue
            polygon = area.get("polygon") or []
            if len(polygon) < 3:
                continue
            rings = [polygon] + [h for h in area.get("holes", []) if len(h) >= 3]
            xs = [p[0] for ring in rings for p in ring]
            ys = [p[1] for ring in rings for p in ring]
            layers = area.get("layers") or set()
            keepouts.append((rings, (min(xs), min(ys), max(xs), max(ys)),
                             set(layers) if layers else None))
        if getattr(self.config, "keepout_enabled", False):
            for zone in getattr(self.pcb, "keepout_zones", None) or []:
                if len(zone.points) >= 3:
                    xs = [p[0] for p in zone.points]
                    ys = [p[1] for p in zone.points]
                    keepouts.append(([list(zone.points)],
                                     (min(xs), min(ys), max(xs), max(ys)), None))
        return keepouts

    def _effective_clearance(self, net_id, layer):
        base = self.clearance
        if self.net_clearances:
            base = max(base, self.net_clearances.get(net_id, base))
        if hasattr(self.config, "layer_clearance"):
            return self.config.layer_clearance(layer, base)
        return base

    def _edge_clears(self, seg, clearance=None):
        required = (self.edge_clearance if clearance is None else clearance) + seg.width / 2.0 - FP_EPS_MM
        endpoints = ((seg.start_x, seg.start_y), (seg.end_x, seg.end_y))
        if self.edge_rings:
            return (all(_point_on_board(x, y, self.edge_outer, self.edge_cutouts)
                        for x, y in endpoints) and
                    _segment_to_rings_distance(
                        seg.start_x, seg.start_y, seg.end_x, seg.end_y,
                        self.edge_rings) >= required)
        if self.board_bounds:
            x0, y0, x1, y1 = self.board_bounds
            return all(min(x - x0, x1 - x, y - y0, y1 - y) >= required
                       for x, y in endpoints)
        return True

    @staticmethod
    def _on_layer(layers, layer):
        return (layers is None or layer in layers or "*.Cu" in layers or
                (layer in ("F.Cu", "B.Cu") and
                 bool({"F&B.Cu", "F&B"} & layers)))

    def _keepouts_clear(self, seg):
        return self._regions_clear(seg, self.keepouts, self.clearance)

    def _regions_clear(self, seg, regions, clearance, all_layers=False):
        margin = clearance + seg.width / 2.0
        for rings, (x0, y0, x1, y1), layers in regions:
            if not all_layers and not self._on_layer(layers, seg.layer):
                continue
            if (max(seg.start_x, seg.end_x) < x0 - margin or
                    min(seg.start_x, seg.end_x) > x1 + margin or
                    max(seg.start_y, seg.end_y) < y0 - margin or
                    min(seg.start_y, seg.end_y) > y1 + margin):
                continue
            inside = sum(point_in_polygon(seg.start_x, seg.start_y, ring)
                         for ring in rings) % 2
            if inside or _segment_to_rings_distance(
                    seg.start_x, seg.start_y, seg.end_x, seg.end_y, rings) < margin - FP_EPS_MM:
                return False
        return True

    def sweep_triangle_clears(self, points, template):
        """Validate a filled triangular axis sweep plus the REAL copper radius.

        KRT checks its three boundary capsules. An obstacle wholly enclosed by
        the triangle need not touch that boundary: test a representative of
        every connected obstacle component too. No raster or enlarged probe.
        Degenerate triangles are simply the union of their boundary segments.
        Guarantees are those of the underlying KRT distance predicates.
        """
        for a, b in zip(points, points[1:] + points[:1]):
            if not self.segment_clears(Segment(*a, *b, template.width,
                                               template.layer, template.net_id)):
                return False
        a, b, c = points
        if (b[0]-a[0])*(c[1]-a[1]) == (b[1]-a[1])*(c[0]-a[0]):
            return True

        def inside(p):
            return point_in_polygon(*p, points)

        x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
        x1, y1 = max(p[0] for p in points), max(p[1] for p in points)

        def enclosed(nid, xs, ys):
            near = ((nid != template.net_id) & (xs >= x0) & (xs <= x1) &
                    (ys >= y0) & (ys <= y1))
            return any(inside((x, y)) for x, y in zip(xs[near], ys[near]))

        # Use KRT's own obstacle arrays, including wildcard-layer vias,
        # custom-pad components and offset/slot NPTH hole axes.
        from .krt_api import _foreign_pad_arrays, _foreign_hole_capsules
        prepared = self._prepared_copper(template.layer)
        arrays = prepared[0] if prepared is not None else _foreign_seg_arrays(self.pcb, template.layer)
        nid, ax, ay, _bx, _by, _half = arrays
        if enclosed(nid, ax, ay):
            return False
        pads = _foreign_pad_arrays(self.pcb, template.layer)
        if enclosed(pads[0], pads[1], pads[2]):
            return False
        for net_id, pad in pads[-1]:
            if net_id != template.net_id and any(
                    poly and inside(poly[0]) for poly in pad.polygons):
                return False
        nid, ax, ay, _bx, _by, _r, _lc = _foreign_hole_capsules(self.pcb)
        if enclosed(nid, ax, ay):
            return False
        for rings, _bounds, layers in self.keepouts:
            if self._on_layer(layers, template.layer) and any(
                    ring and inside(ring[0]) for ring in rings):
                return False
        if any(ring and inside(ring[0]) for ring in self.edge_rings):
            return False
        return True

    def segment_clears(self, seg):
        batch = getattr(self, "_copper_batch", None)
        if batch is None:
            return self._segment_clears(seg)
        certificates = batch.setdefault("certificates", {})
        key = (seg.net_id, seg.layer, seg.width, seg.start_x, seg.start_y,
               seg.end_x, seg.end_y)
        if key in certificates:
            self.copper_data_stats["certificate_hits"] += 1
            return certificates[key]
        clear = self._segment_clears(seg)
        certificates[key] = clear
        return clear

    def _segment_clears(self, seg):
        effective = self._effective_clearance(seg.net_id, seg.layer)
        distance = min(
            self._pad_distance(
                seg.net_id, seg.start_x, seg.start_y,
                seg.end_x, seg.end_y, seg.layer, effective, seg.width/2),
            _exact_foreign_segment_distance(
                self.pcb, seg.net_id, seg.start_x, seg.start_y,
                seg.end_x, seg.end_y, seg.layer,
                net_clearances=self.net_clearances, base_clearance=effective,
                track_clearances=self.track_clearances,
                prepared_copper=self._prepared_copper(seg.layer), half_width=seg.width/2))
        hole_distance = _exact_foreign_hole_distance(
            self.pcb, seg.net_id, seg.start_x, seg.start_y,
            seg.end_x, seg.end_y, self.npth_clearance)
        return (distance >= effective + seg.width / 2.0 - FP_EPS_MM and
                hole_distance >= self.npth_clearance + seg.width / 2.0 - FP_EPS_MM and
                self._edge_clears(seg) and self._keepouts_clear(seg))

    def connector_clears(self, segments):
        return bool(segments) and all(self.segment_clears(seg) for seg in segments)

    def via_sweep_clears(self, old, new):
        """Translate the physical copper cylinder and drill, using KRT capsules.

        A disk translated along a line sweeps exactly a capsule. The two
        diameters are physical dimensions, never increased with displacement.
        KRT's current through-via/layer and rule policies match via_clears.
        """
        if (old.size, old.drill, old.net_id, old.layers) != (
                new.size, new.drill, new.net_id, new.layers):
            return False
        own = max(self.clearance, (self.net_clearances or {}).get(old.net_id, self.clearance))
        hole_clearance = (getattr(self.config, 'hole_to_hole_clearance', None)
                          or HOLE_TO_HOLE_CLEARANCE)
        def sweep(width, layer='F.Cu'):
            return Segment(old.x, old.y, new.x, new.y, width, layer, old.net_id)
        copper, drill = sweep(old.size), sweep(old.drill)
        for seg in self.pcb.segments:
            if seg.net_id == old.net_id or not seg.layer.endswith('.Cu'):
                continue
            pair = self.config.stack_clearance(max(
                own, (self.net_clearances or {}).get(seg.net_id, self.clearance)))
            if check_segment_overlap(sweep(old.size, seg.layer), seg, pair, 0.)[0]:
                return False
        for via in self.pcb.vias:
            if via is old:
                continue
            fixed_drill = Segment(via.x, via.y, via.x, via.y, via.drill, 'F.Cu', via.net_id)
            if check_segment_overlap(drill, fixed_drill, hole_clearance, 0.)[0]:
                return False
            if via.net_id != old.net_id:
                pair = self.config.stack_clearance(max(
                    own, (self.net_clearances or {}).get(via.net_id, self.clearance)))
                if check_via_segment_overlap(via, copper, pair, 0.)[0]:
                    return False
        for net_id, pads in self.pcb.pads_by_net.items():
            for pad in pads:
                if getattr(pad, 'drill', 0.) > 0:
                    a, b, radius = pad_drill_capsule(pad)
                    fixed_drill = Segment(*a, *b, 2*radius, 'F.Cu', net_id)
                    if check_segment_overlap(drill, fixed_drill, hole_clearance, 0.)[0]:
                        return False
                if net_id == old.net_id:
                    continue
                layers = pad_copper_layers(pad, self.pcb.board_info.copper_layers)
                pair = pads_shared_layer_clearance(max(
                    own, (self.net_clearances or {}).get(net_id, self.clearance)),
                    getattr(self.config, 'layer_clearances', None), layers)
                pair = self.config.pad_override_clearance(pair, pad)
                if layers and pad_axis_distance((old.x, old.y), (new.x, new.y), pad) < pair + old.size/2 - FP_EPS_MM:
                    return False
        edge = max(own, getattr(self.config, 'board_edge_clearance', 0.))
        return (self._edge_clears(copper, edge) and
                self._regions_clear(copper, self.via_keepouts, own, all_layers=True))

    def via_clears(self, via, ignored_via=None):
        """Validate a moved via by composing KRT's exact DRC primitives."""
        own = max(self.clearance,
                  (self.net_clearances or {}).get(via.net_id, self.clearance))
        hole_to_hole = (getattr(
            self.config, "hole_to_hole_clearance", None) or
            HOLE_TO_HOLE_CLEARANCE)

        for seg in self.pcb.segments:
            if seg.net_id == via.net_id:
                continue
            pair = max(own, (self.net_clearances or {}).get(seg.net_id,
                                                          self.clearance))
            pair = self.config.stack_clearance(pair)
            if check_via_segment_overlap(via, seg, pair, 0.0)[0]:
                return False
        for other in self.pcb.vias:
            if other is ignored_via:
                continue
            if other.net_id == via.net_id:
                # KRT/KiCad permit same-net copper overlap, but drill spacing is
                # a manufacturing rule independent of electrical net identity.
                if check_via_drill_overlap(
                        via, other, hole_to_hole, 0.0)[0]:
                    return False
                continue
            pair = max(own, (self.net_clearances or {}).get(other.net_id,
                                                          self.clearance))
            pair = self.config.stack_clearance(pair)
            if check_via_via_overlap(via, other, pair, 0.0)[0]:
                return False
            if check_via_drill_overlap(
                    via, other, hole_to_hole, 0.0)[0]:
                return False
        for pad_net, pads in self.pcb.pads_by_net.items():
            for pad in pads:
                if getattr(pad, "drill", 0.0) and check_pad_drill_via_overlap(
                        pad, via, hole_to_hole, 0.0)[0]:
                    return False
                if pad_net == via.net_id:
                    continue
                pair = max(own, (self.net_clearances or {}).get(
                    pad_net, self.clearance))
                copper = pad_copper_layers(
                    pad, self.pcb.board_info.copper_layers)
                pair = pads_shared_layer_clearance(
                    pair, getattr(self.config, "layer_clearances", None),
                    copper)
                pair = self.config.pad_override_clearance(pair, pad)
                if check_pad_via_overlap(
                    pad, via, pair, self.config.layers, 0.0)[0]:
                    return False

        edge = max(own, getattr(self.config, "board_edge_clearance", 0.0))
        if self.edge_rings:
            if check_via_board_edge_poly(
                    via, self.edge_rings, self.edge_outer,
                    self.edge_cutouts, edge, 0.0)[0]:
                return False
        elif self.board_bounds and check_via_board_edge(
                via, self.board_bounds, edge, 0.0)[0]:
            return False

        margin = via.size / 2.0 + own
        for rings, (x0, y0, x1, y1), _layers in self.via_keepouts:
            if not (x0 - margin <= via.x <= x1 + margin and
                    y0 - margin <= via.y <= y1 + margin):
                continue
            inside = False
            for ring in rings:
                if point_in_polygon(via.x, via.y, ring):
                    inside = not inside
            if inside or any(point_to_polygon_edge_distance(
                    via.x, via.y, ring) < margin for ring in rings):
                return False
        return True
