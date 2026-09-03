"""Thin adapter over KRT's existing obstacle-map machinery."""

from dataclasses import dataclass, replace
from collections import Counter

from cleanup_pipeline import _smooth_skip_net_ids
from obstacle_cache import (build_working_obstacle_map,
                            precompute_all_net_obstacles,
                            add_net_obstacles_from_cache,
                            precompute_net_obstacles,
                            remove_net_obstacles_from_cache)
from obstacle_map import build_base_obstacle_map
from routing_config import GridCoord
from routing_utils import build_layer_map

from .krt_clearance import KrtClearanceAdapter


@dataclass
class GlossContext:
    pcb_data: object
    config: object
    coord: GridCoord
    layer_map: dict
    net_ids: list
    working_obstacles: object
    net_obstacles: dict
    clearance_adapter: object
    excluded_net_ids: set
    exclusion_reasons: dict
    foreign_working: object = None
    foreign_excluded_net_id: object = None

    def foreign_obstacles(self, net_id):
        """Reusable KRT obstacle map with only ``net_id`` copper removed."""
        if self.foreign_working is None:
            self.foreign_working = self.working_obstacles.clone_fresh()
        elif self.foreign_excluded_net_id == net_id:
            return self.foreign_working
        else:
            previous = self.net_obstacles.get(self.foreign_excluded_net_id)
            if previous is not None:
                add_net_obstacles_from_cache(self.foreign_working, previous)
        own_cache = self.net_obstacles.get(net_id)
        if own_cache is not None:
            remove_net_obstacles_from_cache(self.foreign_working, own_cache)
        self.foreign_excluded_net_id = net_id
        return self.foreign_working

    def refresh_net_obstacles(self, net_id):
        """Incrementally replace one changed net in the persistent KRT map."""
        old_cache = self.net_obstacles.get(net_id)
        if old_cache is not None:
            remove_net_obstacles_from_cache(self.working_obstacles, old_cache)
            if (self.foreign_working is not None and
                    self.foreign_excluded_net_id != net_id):
                remove_net_obstacles_from_cache(
                    self.foreign_working, old_cache)
        new_cache = precompute_net_obstacles(
            self.pcb_data, net_id, self.config, extra_clearance=0.0)
        self.net_obstacles[net_id] = new_cache
        add_net_obstacles_from_cache(self.working_obstacles, new_cache)
        if (self.foreign_working is not None and
                self.foreign_excluded_net_id != net_id):
            add_net_obstacles_from_cache(self.foreign_working, new_cache)


def _linearized_arc_net_ids(pcb_data):
    """Recognize text-parsed KRT arc chords by their shared native UUID."""
    counts = Counter(segment.uuid for segment in pcb_data.segments
                     if getattr(segment, "uuid", ""))
    repeated = {uuid for uuid, count in counts.items() if count > 1}
    return {segment.net_id for segment in pcb_data.segments
            if getattr(segment, "uuid", "") in repeated and segment.net_id}


def resolve_gloss_scope(pcb_data, net_ids=None, excluded_net_ids=None):
    """G0: resolve the requested scope and every immutable net exactly once."""
    present = {segment.net_id for segment in pcb_data.segments
               if segment.net_id}
    requested = set(net_ids or ())
    scope = present if not requested else present.intersection(requested)
    protected = set(_smooth_skip_net_ids(pcb_data))
    arcs = _linearized_arc_net_ids(pcb_data)
    external = set(excluded_net_ids or ())
    excluded = scope.intersection(protected | arcs | external)
    reasons = {}
    for net_id in excluded:
        labels = []
        if net_id in protected:
            labels.append("KRT protected")
        if net_id in arcs or net_id in external:
            labels.append("arc")
        reasons[net_id] = ", ".join(labels)
    return sorted(scope - excluded), excluded, reasons


def build_gloss_context(pcb_data, config, net_ids=None, *,
                        excluded_net_ids=None, exclusion_reasons=None):
    """Rebuild KRT obstacles from the post-smooth board."""
    layers = list(pcb_data.board_info.copper_layers or config.layers)
    gloss_config = replace(config, layers=layers)
    present_net_ids = {s.net_id for s in pcb_data.segments if s.net_id}
    net_ids = sorted(present_net_ids if net_ids is None
                     else present_net_ids.intersection(net_ids))
    net_clearances = getattr(gloss_config, "net_clearances", None) or None
    gloss_config.set_net_clearances(net_clearances, net_ids)
    base = build_base_obstacle_map(
        pcb_data, gloss_config, net_ids,
        net_clearances=net_clearances, static_base=True)
    caches = precompute_all_net_obstacles(
        pcb_data, net_ids, gloss_config, extra_clearance=0.0)
    working = build_working_obstacle_map(base, caches)
    return GlossContext(
        pcb_data=pcb_data,
        config=gloss_config,
        coord=GridCoord(gloss_config.grid_step),
        layer_map=build_layer_map(layers),
        net_ids=net_ids,
        working_obstacles=working,
        net_obstacles=caches,
        clearance_adapter=KrtClearanceAdapter(pcb_data, gloss_config),
        excluded_net_ids=set(excluded_net_ids or ()),
        exclusion_reasons=dict(exclusion_reasons or {}),
    )
