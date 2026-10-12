"""Gloss-owned adaptations of the unmodified KRT fill model.

KRT still builds and queries every bitmap. Its board-local cache and secondary
zone lookup receive the same wrapper; no module/class monkey-patch or shadow
module is installed. Keep knowledge of KRT's private cache layout in this file.
"""

import math

from dgloss.krt_api import plane_fill_model as krt


def _zone_obstacle_subset(pcb_data, zone):
    """Cull only stamps unable to reach KRT's raster, including its guard cells.

    KRT still constructs the entire model. Pads, rules, keepouts and outlines
    remain on the original board. Large zones use the original path: filtering
    a near-board-sized plane rarely saves work. This cutoff affects cost only.
    """
    from .clearance_preparation import BoardSubset

    thickness = (zone.min_thickness if zone.min_thickness is not None else
                 krt.defaults.PLANE_MIN_THICKNESS)
    cell = min(.08, max(.04, thickness / 2))
    xs, ys = zip(*zone.polygon)
    x0, y0 = min(xs) - cell, min(ys) - cell
    nx = int((max(xs) - x0) / cell) + 2
    ny = int((max(ys) - y0) / cell) + 2
    if nx <= 2 or ny <= 2 or nx * ny > 30_000_000:
        return pcb_data  # retain KRT's unsupported-model policy
    x1, y1 = x0 + nx * cell, y0 + ny * cell
    bounds = getattr(pcb_data.board_info, 'board_bounds', None)
    if bounds:
        bx0, by0, bx1, by1 = bounds
        area = (bx1 - bx0) * (by1 - by0)
        if area > 0 and (x1 - x0) * (y1 - y0) >= area / 4:
            return pcb_data
    rules = getattr(pcb_data, krt._NC_ATTR, None) or {}
    clearance = max(zone.clearance if zone.clearance is not None else
                    krt.defaults.PLANE_ZONE_CLEARANCE, rules.get(zone.net_id, 0.))

    def overlaps(ax, ay, bx, by, radius, net):
        margin = max(clearance, rules.get(net, 0.)) + radius + 2 * cell
        # Outward rounding and two spare cells cover KRT's integer windows.
        return not (max(ax, bx) < math.nextafter(x0 - margin, -math.inf) or
                    min(ax, bx) > math.nextafter(x1 + margin, math.inf) or
                    max(ay, by) < math.nextafter(y0 - margin, -math.inf) or
                    min(ay, by) > math.nextafter(y1 + margin, math.inf))

    segments = [s for s in pcb_data.segments
                if s.net_id != zone.net_id and s.layer == zone.layer and
                overlaps(s.start_x, s.start_y, s.end_x, s.end_y,
                         s.width / 2, s.net_id)]
    # KRT stamps foreign vias on every layer; do not narrow their layer scope.
    vias = [v for v in pcb_data.vias if v.net_id != zone.net_id and
            overlaps(v.x, v.y, v.x, v.y, v.size / 2, v.net_id)]
    return BoardSubset(pcb_data, segments=segments, vias=vias)


def reset_copper_models(pcb_data):
    """Discard derived fills after rollback, including KRT's secondary lookup."""
    cache = getattr(pcb_data, krt._CACHE_ATTR, None) or {}
    for key, model in list(cache.items()):
        if krt._MODELS_BY_ZONE_ID.get(key[2]) is model:
            krt._MODELS_BY_ZONE_ID.pop(key[2], None)
    setattr(pcb_data, krt._CACHE_ATTR, {})


class CachedZoneModel:
    """Delegate to an immutable KRT model; memoize only its largest component."""

    def __init__(self, model):
        self._model = model
        self._largest_component_id = None

    def __getattr__(self, name):
        return getattr(self._model, name)

    def largest_component(self):
        if self._largest_component_id is None:
            self._largest_component_id = self._model.largest_component()
        return self._largest_component_id


def prepare_zone_models(pcb_data, zones):
    """Prepare only the requested net's models before KRT connectivity queries."""
    for zone in zones:
        if not getattr(zone, "polygon", None):
            continue
        try:
            try:
                cache = getattr(pcb_data, krt._CACHE_ATTR, None)
                if cache is None:
                    cache = {}
                    setattr(pcb_data, krt._CACHE_ATTR, cache)
                key = (zone.net_id, zone.layer, id(zone))
                if cache.get(key) is None:
                    subset = _zone_obstacle_subset(pcb_data, zone)
                    if subset is not pcb_data:
                        # The view delegates the board-local cache. Let KRT
                        # publish its secondary entry and enforce its capacity.
                        krt.get_zone_model(subset, zone)
            except Exception:
                # A failed broad phase must still try KRT on the full board.
                pass
            model = krt.get_zone_model(pcb_data, zone)
        except Exception:
            # KRT connectivity itself catches model-construction failures and
            # falls back to its legacy zone test; do not change that policy here.
            continue
        if model is None:
            continue  # retain KRT's unsupported-model fallback
        if not isinstance(model, CachedZoneModel):
            cache = getattr(pcb_data, krt._CACHE_ATTR, None)
            if cache is None:
                continue
            model = CachedZoneModel(model)
            cache[(zone.net_id, zone.layer, id(zone))] = model
        # get_fill_models may have built the board-local entry without populating
        # the secondary lookup. Publish the same object for both call paths.
        if len(krt._MODELS_BY_ZONE_ID) > 64:
            krt._MODELS_BY_ZONE_ID.clear()
        krt._MODELS_BY_ZONE_ID[id(zone)] = model


def invalidate_copper_models(pcb_data, segments=(), vias=()):
    """Invalidate cached fills affected by committed old/new foreign copper.

    Same-net copper is not subtracted by KRT. Via stamps affect every layer.
    Whole affected models are replaced lazily, never patched cell by cell.
    Pads, rules and outline changes require a full reset outside this API.
    """
    segments, vias = tuple(segments), tuple(vias)
    cache = getattr(pcb_data, krt._CACHE_ATTR, None) or {}
    affected = set()
    net_rules = getattr(pcb_data, krt._NC_ATTR, None) or {}
    zones = {id(z): z for z in (getattr(pcb_data, "zones", None) or [])}
    for key, model in list(cache.items()):
        zone = zones.get(key[2])
        if zone is None or not model.ok:
            continue
        clearance = max(zone.clearance if zone.clearance is not None else
                        krt.defaults.PLANE_ZONE_CLEARANCE, net_rules.get(zone.net_id, 0))
        bbox = (model.x0, model.y0, model.x0 + model.nx * model.cell,
                model.y0 + model.ny * model.cell)

        def overlaps(item, via=False):
            if item.net_id == zone.net_id or (not via and item.layer != zone.layer):
                return False
            margin = max(clearance, net_rules.get(item.net_id, 0)) + 2 * model.cell
            if via:
                x0 = x1 = item.x
                y0 = y1 = item.y
                margin += item.size / 2
            else:
                x0, x1 = sorted((item.start_x, item.end_x))
                y0, y1 = sorted((item.start_y, item.end_y))
                margin += item.width / 2
            return not (x1 + margin < bbox[0] or x0 - margin > bbox[2] or
                        y1 + margin < bbox[1] or y0 - margin > bbox[3])

        if any(overlaps(s) for s in segments) or any(overlaps(v, True) for v in vias):
            cache.pop(key, None)
            # A different PCB snapshot may own the secondary entry by now.
            if krt._MODELS_BY_ZONE_ID.get(id(zone)) is model:
                krt._MODELS_BY_ZONE_ID.pop(id(zone), None)
            affected.add(zone.net_id)
    return affected
