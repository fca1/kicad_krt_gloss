"""G3 clearance adapter: KRT owns every geometry and rule calculation."""

import math

from check_drc import (board_edge_geometry, check_pad_drill_via_overlap,
                       check_pad_via_overlap, check_via_board_edge,
                       check_via_drill_overlap,
                       check_via_board_edge_poly, check_via_segment_overlap,
                       check_via_via_overlap, pad_copper_layers,
                       pads_shared_layer_clearance, _point_on_board,
                       _segment_to_rings_distance)
from obstacle_map import point_in_polygon, point_to_polygon_edge_distance
from routing_defaults import HOLE_TO_HOLE_CLEARANCE, NPTH_TO_TRACK_CLEARANCE
from single_ended_routing import (_seg_foreign_hole_dist,
                                  _seg_foreign_pad_dist,
                                  _seg_foreign_seg_dist,
                                  _seg_foreign_via_dist)


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

    def _edge_clears(self, seg):
        required = self.edge_clearance + seg.width / 2.0 - 1e-4
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
        margin = self.clearance + seg.width / 2.0
        for rings, (x0, y0, x1, y1), layers in self.keepouts:
            if not self._on_layer(layers, seg.layer):
                continue
            if (max(seg.start_x, seg.end_x) < x0 - margin or
                    min(seg.start_x, seg.end_x) > x1 + margin or
                    max(seg.start_y, seg.end_y) < y0 - margin or
                    min(seg.start_y, seg.end_y) > y1 + margin):
                continue
            samples = max(2, int(math.hypot(seg.end_x - seg.start_x,
                                            seg.end_y - seg.start_y) / 0.1) + 1)
            for index in range(samples + 1):
                t = index / samples
                x = seg.start_x + t * (seg.end_x - seg.start_x)
                y = seg.start_y + t * (seg.end_y - seg.start_y)
                inside = False
                for ring in rings:
                    if point_in_polygon(x, y, ring):
                        inside = not inside
                if inside or any(point_to_polygon_edge_distance(x, y, ring) < margin
                                 for ring in rings):
                    return False
        return True

    def segment_clears(self, seg):
        effective = self._effective_clearance(seg.net_id, seg.layer)
        distance = min(
            _seg_foreign_pad_dist(
                self.pcb, seg.net_id, seg.start_x, seg.start_y,
                seg.end_x, seg.end_y, seg.layer, base_clearance=effective,
                net_clearances=self.net_clearances),
            _seg_foreign_seg_dist(
                self.pcb, seg.net_id, seg.start_x, seg.start_y,
                seg.end_x, seg.end_y, seg.layer,
                net_clearances=self.net_clearances, base_clearance=effective,
                track_clearances=self.track_clearances),
            _seg_foreign_via_dist(
                self.pcb, seg.net_id, seg.start_x, seg.start_y,
                seg.end_x, seg.end_y, seg.layer,
                net_clearances=self.net_clearances, base_clearance=effective))
        hole_distance = _seg_foreign_hole_dist(
            self.pcb, seg.net_id, seg.start_x, seg.start_y,
            seg.end_x, seg.end_y)
        return (distance >= effective + seg.width / 2.0 - 1e-4 and
                hole_distance >= self.npth_clearance + seg.width / 2.0 - 1e-4 and
                self._edge_clears(seg) and self._keepouts_clear(seg))

    def connector_clears(self, segments):
        return bool(segments) and all(self.segment_clears(seg) for seg in segments)

    def via_clears(self, via, ignored_via=None):
        """Validate a moved via by composing KRT's exact DRC primitives."""
        own = max(self.clearance,
                  (self.net_clearances or {}).get(via.net_id, self.clearance))

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
                        via, other, HOLE_TO_HOLE_CLEARANCE, 0.0)[0]:
                    return False
                continue
            pair = max(own, (self.net_clearances or {}).get(other.net_id,
                                                          self.clearance))
            pair = self.config.stack_clearance(pair)
            if check_via_via_overlap(via, other, pair, 0.0)[0]:
                return False
            if check_via_drill_overlap(
                    via, other, HOLE_TO_HOLE_CLEARANCE, 0.0)[0]:
                return False
        for pad_net, pads in self.pcb.pads_by_net.items():
            for pad in pads:
                if getattr(pad, "drill", 0.0) and check_pad_drill_via_overlap(
                        pad, via, HOLE_TO_HOLE_CLEARANCE, 0.0)[0]:
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
                pair = max(pair, getattr(pad, "local_clearance", 0.0) or 0.0)
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
