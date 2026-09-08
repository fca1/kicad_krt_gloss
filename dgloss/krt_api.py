"""Single import boundary between Gloss and the unmodified KRT library.

Configure the KRT runtime before using this API. Symbols are resolved lazily
so optional placement and GUI dependencies remain optional. Once resolved,
callers receive the original callable/type: no per-call dispatch, conversion,
copy or additional geometry cache. Adapt renamed symbols/signatures here when
KRT evolves; keep geometry and validation authority in KRT.

Clearance composition and zone-cache compatibility remain in krt_clearance.py
and zone_models.py. The runtime bootstrap is necessarily outside this boundary.
"""

from importlib import import_module

# Local API name -> (KRT module, attribute); None exposes a module.
_EXPORTS = {
    'COINCIDENCE_TOL': ('connectivity', 'COINCIDENCE_TOL'),
    'DesignRules': ('design_rules', 'DesignRules'),
    'FP_EPS_MM': ('check_drc', 'FP_EPS_MM'),
    'GridCoord': ('routing_config', 'GridCoord'),
    'GridRouteConfig': ('routing_config', 'GridRouteConfig'),
    'GroupError': ('placement.groups', 'GroupError'),
    'GroupRoutingError': ('group_routing', 'GroupRoutingError'),
    'HOLE_TO_HOLE_CLEARANCE': ('routing_defaults', 'HOLE_TO_HOLE_CLEARANCE'),
    'NPTH_TO_TRACK_CLEARANCE': ('routing_defaults', 'NPTH_TO_TRACK_CLEARANCE'),
    'NetSelectionPanel': ('kicad_routing_plugin.fanout_gui', 'NetSelectionPanel'),
    'POWER_NET_EXCLUSION_PATTERNS': ('routing_constants', 'POWER_NET_EXCLUSION_PATTERNS'),
    'Segment': ('kicad_parser', 'Segment'),
    'SpatialIndex': ('check_drc', 'SpatialIndex'),
    'UnionFind': ('geometry_utils', 'UnionFind'),
    '_FOREIGN_PAD_WINDOW': ('single_ended_routing', '_FOREIGN_PAD_WINDOW'),
    '_foreign_seg_arrays': ('single_ended_routing', '_foreign_seg_arrays'),
    '_foreign_pad_arrays': ('single_ended_routing', '_foreign_pad_arrays'),
    '_pad_corner_radius': ('single_ended_routing', '_pad_corner_radius'),
    '_foreign_hole_capsules': ('single_ended_routing', '_foreign_hole_capsules'),
    '_octolinear_bends': ('pcb_modification', '_octolinear_bends'),
    '_placer_path': ('_placer_path', None),
    '_point_on_board': ('check_drc', '_point_on_board'),
    '_seg_capsule_axis_dist': ('single_ended_routing', '_seg_capsule_axis_dist'),
    '_seg_foreign_hole_dist': ('single_ended_routing', '_seg_foreign_hole_dist'),
    '_seg_foreign_pad_dist': ('single_ended_routing', '_seg_foreign_pad_dist'),
    '_seg_foreign_via_dist': ('single_ended_routing', '_seg_foreign_via_dist'),
    '_segment_fits_wide': ('single_ended_routing', '_segment_fits_wide'),
    '_segment_to_polys_distance': ('check_drc', '_segment_to_polys_distance'),
    '_segment_to_rings_distance': ('check_drc', '_segment_to_rings_distance'),
    '_smooth_skip_net_ids': ('cleanup_pipeline', '_smooth_skip_net_ids'),
    'add_net_obstacles_from_cache': ('obstacle_cache', 'add_net_obstacles_from_cache'),
    'block_net_names': ('group_routing', 'block_net_names'),
    'block_refs': ('group_routing', 'block_refs'),
    'board_default_netclass_clearance': ('list_nets', 'board_default_netclass_clearance'),
    'board_default_netclass_param': ('list_nets', 'board_default_netclass_param'),
    'board_edge_geometry': ('check_drc', 'board_edge_geometry'),
    'build_base_obstacle_map': ('obstacle_map', 'build_base_obstacle_map'),
    'build_layer_map': ('routing_utils', 'build_layer_map'),
    'build_pcb_data_from_board': ('kicad_parser', 'build_pcb_data_from_board'),
    'build_working_obstacle_map': ('obstacle_cache', 'build_working_obstacle_map'),
    'calculate_route_length': ('net_queries', 'calculate_route_length'),
    'check_net_connectivity': ('check_connected', 'check_net_connectivity'),
    'check_pad_drill_via_overlap': ('check_drc', 'check_pad_drill_via_overlap'),
    'check_pad_via_overlap': ('check_drc', 'check_pad_via_overlap'),
    'check_segment_overlap': ('check_drc', 'check_segment_overlap'),
    'pad_drill_capsule': ('kicad_parser', 'pad_drill_capsule'),
    'check_via_board_edge': ('check_drc', 'check_via_board_edge'),
    'check_via_board_edge_poly': ('check_drc', 'check_via_board_edge_poly'),
    'check_via_drill_overlap': ('check_drc', 'check_via_drill_overlap'),
    'check_via_segment_overlap': ('check_drc', 'check_via_segment_overlap'),
    'check_via_via_overlap': ('check_drc', 'check_via_via_overlap'),
    'copy_board': ('copy_board', 'copy_board'),
    'derive_groups': ('placement.groups', 'derive_groups'),
    'describe_scope': ('group_routing', 'describe_scope'),
    'expand_net_patterns': ('net_queries', 'expand_net_patterns'),
    'find_matching_paren': ('kicad_parser', 'find_matching_paren'),
    'generate_gr_line_sexpr': ('kicad_writer', 'generate_gr_line_sexpr'),
    'install_layer_clearances': ('kicad_dru', 'install_layer_clearances'),
    'install_track_clearances': ('kicad_dru', 'install_track_clearances'),
    'merge_collinear_segments': ('pcb_modification', 'merge_collinear_segments'),
    'mm_to_iu': ('kicad_parser', 'mm_to_iu'),
    'net_clearance_map_by_id': ('list_nets', 'net_clearance_map_by_id'),
    'net_copper_length': ('net_queries', 'net_copper_length'),
    'nets_for_components': ('net_queries', 'nets_for_components'),
    'pad_copper_layers': ('check_drc', 'pad_copper_layers'),
    'pads_shared_layer_clearance': ('check_drc', 'pads_shared_layer_clearance'),
    'parse_kicad_pcb': ('kicad_parser', 'parse_kicad_pcb'),
    'parse_sources': ('placement.groups', 'parse_sources'),
    'plane_fill_model': ('plane_fill_model', None),
    'point_in_polygon': ('obstacle_map', 'point_in_polygon'),
    'point_to_pad_distance': ('check_drc', 'point_to_pad_distance'),
    'point_to_polygon_edge_distance': ('obstacle_map', 'point_to_polygon_edge_distance'),
    'point_to_segment_distance': ('geometry_utils', 'point_to_segment_distance'),
    'pos_key': ('routing_utils', 'pos_key'),
    'precompute_all_net_obstacles': ('obstacle_cache', 'precompute_all_net_obstacles'),
    'precompute_net_obstacles': ('obstacle_cache', 'precompute_net_obstacles'),
    'record_invocation': ('redo_record', 'record_invocation'),
    'remove_net_obstacles_from_cache': ('obstacle_cache', 'remove_net_obstacles_from_cache'),
    'resolve_cli_floor': ('list_nets', 'resolve_cli_floor'),
    'resolve_net_ids': ('routing_common', 'resolve_net_ids'),
    'resolved_name': ('group_routing', 'resolved_name'),
    'routing_defaults': ('routing_defaults', None),
    'segment_to_rect_distance': ('check_drc', 'segment_to_rect_distance'),
    'segments_intersect': ('geometry_utils', 'segments_intersect'),
    'short_name': ('placement.groups', 'short_name'),
    'smooth_octolinear_chains': ('pcb_modification', 'smooth_octolinear_chains'),
    'suggest_component_refs': ('net_queries', 'suggest_component_refs'),
    'via_copper_layers': ('connectivity', 'via_copper_layers'),
    'write_routed_output': ('output_writer', 'write_routed_output'),
}


def __getattr__(name):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"{__name__!r} has no attribute {name!r}") from None
    module = import_module(module_name)
    value = module if attribute is None else getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
