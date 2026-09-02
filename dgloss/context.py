"""Thin adapter over KRT's existing obstacle-map machinery."""

from dataclasses import dataclass, replace

from obstacle_cache import (build_working_obstacle_map,
                            precompute_all_net_obstacles)
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


def build_gloss_context(pcb_data, config, net_ids=None):
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
    )
