#!/usr/bin/env python3
"""Targeted acceptance tests for Track Gloss milestones G0, G1 and G3."""

import math
import os
import sys
import types
from collections import defaultdict
from unittest.mock import patch

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KRT = os.path.join(REPO, "KRT")
for path in (REPO, KRT, os.path.join(KRT, "py_router"),
             os.path.join(KRT, "rust_router")):
    if path not in sys.path:
        sys.path.insert(0, path)

from dgloss.context import build_gloss_context
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.config import GlossConfig
from dgloss.changes import GlossChanges
from dgloss.comparison import compare_smoothers, format_comparison_table
from dgloss.algorithm import (_Chain, _best_chain_replacement,
                              _candidate_clears,
                              _sliding_candidate_families)
from dgloss.pipeline import (_certify_g5_copper, _g5_grade, _grade,
                             _validate_final, run_final_gloss,
                             run_post_smooth_gloss)
from dgloss.pad_terminals import optimize_pad_terminals
from dgloss.sliding_nodes import slide_t_nodes
from dgloss.via_mobile import move_mobile_vias, refine_mobile_vias
from kicad_krt_gloss.gloss_visualization import (
    _line_parts, add_changes_to_board, add_layer_user,
    disable_intermediate_layers)
from kicad_parser import BoardInfo, Net, Pad, PCBData, Segment, Via
from net_queries import calculate_route_length
from routing_config import GridRouteConfig
from routing_utils import pos_key


def _pad(ref, x, y, net_id, layer="F.Cu"):
    return Pad(ref, "1", x, y, 0.0, 0.0, 0.5, 0.5, "rect", [layer],
               net_id, f"N{net_id}")


def _parallel_board():
    first = Segment(2.0, 5.0, 8.0, 5.0, 0.2, "F.Cu", 1)
    second = Segment(2.0, 6.0, 8.0, 6.0, 0.2, "F.Cu", 2)
    pads = {
        1: [_pad("A", 2.0, 5.0, 1), _pad("B", 8.0, 5.0, 1)],
        2: [_pad("C", 2.0, 6.0, 2), _pad("D", 8.0, 6.0, 2)],
    }
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 10.0, 10.0)),
        {1: Net(1, "N1"), 2: Net(2, "N2")}, {}, [], [first, second], pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.2, grid_step=0.1,
        layers=["F.Cu"], board_edge_clearance=0.2)
    return pcb, config, first, second


def _staircase_board():
    segments = [
        Segment(1.0, 1.0, 2.0, 1.0, 0.2, "F.Cu", 1),
        Segment(2.0, 1.0, 2.0, 2.0, 0.2, "F.Cu", 1),
        Segment(2.0, 2.0, 4.0, 2.0, 0.2, "F.Cu", 1),
    ]
    pads = {1: [_pad("A", 1.0, 1.0, 1), _pad("B", 4.0, 2.0, 1)]}
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 6.0, 4.0)),
        {1: Net(1, "N1")}, {}, [], segments, pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu"], board_edge_clearance=0.0)
    return pcb, config, segments


def _blocked_canonical_board():
    segments = [
        Segment(1.0, 1.0, 5.0, 1.0, 0.2, "F.Cu", 1),
        Segment(5.0, 1.0, 6.0, 2.0, 0.2, "F.Cu", 1),
        Segment(6.0, 2.0, 6.0, 8.0, 0.2, "F.Cu", 1),
    ]
    pads = {
        1: [_pad("A", 1.0, 1.0, 1), _pad("B", 6.0, 8.0, 1)],
        # Each pad blocks one of KRT's two canonical shortest bends.
        2: [_pad("X", 2.0, 2.0, 2), _pad("Y", 2.0, 4.0, 2)],
    }
    pcb = PCBData(
        BoardInfo({}, ["F.Cu"], (0.0, 0.0, 10.0, 10.0)),
        {1: Net(1, "N1"), 2: Net(2, "N2")}, {}, [], segments, pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu"], board_edge_clearance=0.0)
    return pcb, config, segments


def test_g0_rebuilds_all_layers_with_krt_rust_map():
    pcb, config, _first, _second = _parallel_board()
    context = build_gloss_context(pcb, config)
    assert context.net_ids == [1, 2]
    assert set(context.layer_map) == {"F.Cu", "B.Cu"}
    assert context.working_obstacles is not None
    assert hasattr(context.working_obstacles, "segment_blocked")


def test_dgloss_runtime_has_no_pcbnew_or_plugin_dependency():
    runtime_dir = os.path.join(REPO, "dgloss")
    for name in os.listdir(runtime_dir):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(runtime_dir, name), encoding="utf-8") as handle:
            source = handle.read()
        assert "pcbnew" not in source, name
        assert "kicad_routing_plugin" not in source, name


def test_g3_5_config_defaults_enable_every_optional_stage():
    config = GlossConfig()
    assert config.enable_g3_1
    assert config.enable_g3_2
    assert config.enable_g3_3
    assert config.enable_g3_4
    assert config.enable_noncollinear_t_rails
    assert config.enable_multipasses
    assert config.budget_seconds == 20.0


def test_g0_post_smooth_entry_never_runs_krt_smooth_again():
    pcb, config, _first, _second = _parallel_board()
    disabled = GlossConfig(False, False, False, False)
    with patch("dgloss.pipeline.smooth_octolinear_chains") as smooth:
        outcome = run_post_smooth_gloss([], pcb, config, disabled)
    smooth.assert_not_called()
    assert outcome.stats["config"]["enable_g3_1"] is False
    assert all(not outcome.stats["gloss"]["stages"][stage]["enabled"]
               for stage in ("G3.1", "G3.2", "G3.3", "G3.4"))


def test_empty_net_list_means_all_and_nonempty_list_filters_complete_nets():
    pcb, config, _first, _second = _parallel_board()
    all_nets = run_post_smooth_gloss(
        [], pcb, config, GlossConfig(False, False, False, False), net_ids=[])
    assert all_nets.stats["nets_processed"] == 2

    pcb, config, _first, _second = _parallel_board()
    selected = run_post_smooth_gloss(
        [], pcb, config, GlossConfig(False, False, False, False), net_ids=[2])
    assert selected.stats["nets_processed"] == 1
    assert math.isclose(selected.stats["before_mm"], 6.0)
    assert math.isclose(selected.stats["after_mm"], 6.0)


def test_nonempty_selection_without_routed_copper_does_not_expand_to_all():
    pcb, config, first, second = _parallel_board()
    outcome = run_post_smooth_gloss(
        [], pcb, config, GlossConfig(enable_multipasses=False), net_ids=[99])
    assert outcome.stats["nets_processed"] == 0
    assert pcb.segments == [first, second]
    assert not outcome.changes["segments"]


def test_via_clearance_enforces_same_net_hole_spacing():
    pcb, config, _first, _second = _parallel_board()
    existing = Via(5.0, 5.0, 0.3, 0.2, ["F.Cu", "B.Cu"], 1)
    candidate = Via(5.35, 5.0, 0.3, 0.2, ["F.Cu", "B.Cu"], 1)
    pcb.vias = [existing]
    assert not KrtClearanceAdapter(pcb, config).via_clears(candidate)


def test_via_clearance_honours_foreign_pad_local_clearance():
    pcb, config, _first, _second = _parallel_board()
    pad = pcb.pads_by_net[2][0]
    pad.local_clearance = 0.5
    candidate = Via(2.7, 6.0, 0.3, 0.2, ["F.Cu", "B.Cu"], 1)
    assert not KrtClearanceAdapter(pcb, config).via_clears(candidate)


def test_final_entry_passes_the_same_complete_net_scope_to_krt_and_dgloss():
    pcb, config, _first, _second = _parallel_board()
    disabled = GlossConfig(False, False, False, False)
    with patch("dgloss.pipeline.smooth_octolinear_chains",
               return_value=(0, set(), [], [], {"saved_mm": 0.0})) as smooth:
        outcome = run_final_gloss(
            [], pcb, config, disabled, net_ids=[2])
    assert smooth.call_args.args[2] == [2]
    assert outcome.stats["nets_processed"] == 1


def test_g3_5_each_optional_stage_can_be_disabled_independently():
    targets = {
        "enable_g3_1": ("G3.1", "dgloss.pipeline.move_mobile_vias"),
        "enable_g3_2": ("G3.2", "dgloss.pipeline.optimize_pad_terminals"),
        "enable_g3_3": ("G3.3", "dgloss.pipeline.slide_t_nodes"),
        "enable_g3_4": ("G3.4", "dgloss.pipeline.refine_mobile_vias"),
    }
    for field, (stage, target) in targets.items():
        pcb, config, _first, _second = _parallel_board()
        selected = GlossConfig(**{field: False})
        with patch(target, side_effect=AssertionError("disabled stage ran")):
            outcome = run_post_smooth_gloss([], pcb, config, selected)
        assert outcome.stats["gloss"]["stages"][stage]["enabled"] is False


def test_g3_5_zero_budget_keeps_a_complete_certified_board():
    pcb, config, _segments = _staircase_board()
    before = list(pcb.segments)
    outcome = run_post_smooth_gloss(
        [], pcb, config, GlossConfig(budget_seconds=0.0))
    assert pcb.segments == before
    assert outcome.stats["gloss"]["budget_expired"]
    assert outcome.stats["connectivity_regressions"] == 0


def test_g3_shortens_one_net_without_changing_widths():
    pcb, config, segments = _staircase_board()
    before_length = sum(math.hypot(s.end_x - s.start_x,
                                   s.end_y - s.start_y) for s in pcb.segments)
    results = [{"new_segments": [segments[0]], "new_vias": []}]
    outcome = run_final_gloss(results, pcb, config)
    after_length = sum(math.hypot(s.end_x - s.start_x,
                                  s.end_y - s.start_y) for s in pcb.segments)
    assert after_length < before_length - config.grid_step
    assert all(math.isclose(s.width, 0.2) for s in pcb.segments)
    assert outcome.stats["krt_baseline_saved_mm"] > config.grid_step
    assert outcome.input_strip_segments


def test_g3_krt_adapter_allows_own_terminal_pad():
    """G3 must inherit KRT smooth's same-net terminal-pad semantics."""
    pcb, config, _segments = _staircase_board()
    context = build_gloss_context(pcb, config)
    connector = Segment(1.0, 1.0, 4.0, 2.0, 0.2, "F.Cu", 1)
    assert context.clearance_adapter.connector_clears([connector])


def test_g3_slides_ordinary_diagonal_when_canonical_bends_are_blocked():
    pcb, config, original = _blocked_canonical_board()
    before = calculate_route_length(original)
    results = []
    outcome = run_final_gloss(
        results, pcb, config, GlossConfig(enable_multipasses=False))
    result = [s for s in pcb.segments if s.net_id == 1]
    after = calculate_route_length(result)
    diagonals = [s for s in result
                 if math.isclose(abs(s.end_x - s.start_x),
                                 abs(s.end_y - s.start_y), abs_tol=1e-9)]
    assert after < before - config.grid_step
    assert len(result) == 3 and diagonals
    assert abs(diagonals[0].end_x - diagonals[0].start_x) > 1.0
    slide = result[0].end_x - result[0].start_x
    assert math.isclose(slide / config.grid_step,
                        round(slide / config.grid_step), abs_tol=1e-9)
    assert outcome.stats["nets_changed"] == 1
    assert outcome.stats["nets_processed"] == 1
    assert outcome.stats["segment_changes"] > 0
    assert outcome.stats["via_changes"] == 0
    visible = [result for result in results
               if result.get("track_gloss_changes")]
    assert len(visible) == 1
    assert visible[0]["cleanup"] == "track_gloss_g4_visualization"
    assert visible[0]["new_segments"] == []
    assert all(change.get("stage") == "G4" for kind in ("segments", "vias")
               for change in visible[0]["track_gloss_changes"][kind])


def test_a11_style_grid_rejection_uses_exact_krt_only_for_retained_copper():
    source = Segment(2.0, 1.0, 2.0, 6.0, 0.4, "B.Cu", 1)
    diagonal = Segment(0.0, 0.0, 2.0, 2.0, 0.4, "B.Cu", 1)
    retained = Segment(2.0, 2.0, 2.0, 6.0, 0.4, "B.Cu", 1)
    adapter = types.SimpleNamespace(connector_clears=lambda _segments: True)
    context = types.SimpleNamespace(
        coord=types.SimpleNamespace(grid_step=0.1),
        clearance_adapter=adapter)

    def grid_check(_context, _obstacles, segments):
        return segments[0] is diagonal

    with patch("dgloss.algorithm._clears_krt_grid", side_effect=grid_check):
        assert _candidate_clears(
            context, object(), [diagonal, retained], "sliding", [source])

        new_rejected = Segment(3.0, 2.0, 3.0, 6.0, 0.4, "B.Cu", 1)
        assert not _candidate_clears(
            context, object(), [diagonal, new_rejected], "sliding", [source])


def test_g4_exposes_only_the_final_user1_delta():
    pcb, config, _original = _blocked_canonical_board()
    results = []

    run_final_gloss(results, pcb, config)

    visible = [result for result in results
               if result.get("track_gloss_changes")]
    assert len(visible) == 1
    assert visible[0]["cleanup"] == "track_gloss_g4_visualization"
    assert all(change.get("stage") == "G4"
               for kind in ("segments", "vias")
               for change in visible[0]["track_gloss_changes"][kind])


def test_g3_5_uses_krt_to_merge_equal_length_collinear_segments():
    segments = [
        Segment(1.0, 1.0, 2.0, 1.0, 0.2, "F.Cu", 1),
        Segment(2.0, 1.0, 3.0, 1.0, 0.2, "F.Cu", 1),
        Segment(3.0, 1.0, 5.0, 1.0, 0.2, "F.Cu", 1),
    ]
    pcb = PCBData(
        BoardInfo({}, ["F.Cu"], (0.0, 0.0, 6.0, 3.0)),
        {1: Net(1, "N1")}, {}, [], list(segments),
        {1: [_pad("A", 1.0, 1.0, 1), _pad("B", 5.0, 1.0, 1)]})
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu"], board_edge_clearance=0.0)
    before = calculate_route_length(pcb.segments)
    results = []

    outcome = run_post_smooth_gloss(
        results, pcb, config, GlossConfig(enable_multipasses=False))

    assert len(pcb.segments) == 1
    assert math.isclose(calculate_route_length(pcb.segments), before,
                        abs_tol=1e-12)
    assert outcome.stats["segments_merged"] == 2
    assert outcome.stats["merge_joints"] == 2
    assert outcome.stats["merge_nets_changed"] == 1
    assert len(outcome.input_strip_segments) == 3
    additions = [segment for result in results
                 for segment in result.get("new_segments", [])]
    assert additions == pcb.segments
    assert not {id(segment) for segment in additions}.intersection(
        id(segment) for segment in outcome.input_strip_segments)
    assert outcome.stats["connectivity_regressions"] == 0


def test_g3_5_reduces_noncollinear_chain_at_equal_length():
    segments = [
        Segment(1.0, 1.0, 2.0, 1.0, 0.2, "F.Cu", 1),
        Segment(2.0, 1.0, 3.0, 2.0, 0.2, "F.Cu", 1),
        Segment(3.0, 2.0, 4.0, 2.0, 0.2, "F.Cu", 1),
    ]
    pcb = PCBData(
        BoardInfo({}, ["F.Cu"], (0.0, 0.0, 6.0, 4.0)),
        {1: Net(1, "N1")}, {}, [], list(segments),
        {1: [_pad("A", 1.0, 1.0, 1), _pad("B", 4.0, 2.0, 1)]})
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu"], board_edge_clearance=0.0)
    before = calculate_route_length(pcb.segments)

    outcome = run_post_smooth_gloss(
        [], pcb, config, GlossConfig(enable_multipasses=False))

    assert len(pcb.segments) == 2
    assert math.isclose(calculate_route_length(pcb.segments), before,
                        abs_tol=1e-9)
    assert outcome.stats["equal_length_segment_reduction"] == 1
    assert outcome.stats["segments_merged"] == 0
    assert outcome.stats["connectivity_regressions"] == 0


def test_g3_5_delegates_segment_reduction_to_krt():
    pcb, config, _first, _second = _parallel_board()
    with patch("dgloss.pipeline.merge_collinear_segments",
               return_value=(0, 0, [], [], {
                   "joints": 0, "segs_removed": 0, "segs_added": 0,
                   "nets_skipped_large": 0})) as merge:
        run_post_smooth_gloss(
            [], pcb, config, GlossConfig(enable_multipasses=False))

    assert merge.call_count == 1
    assert merge.call_args.args[2] == {1, 2}


def test_g3_5_segment_reduction_respects_selected_complete_net_scope():
    segments = [
        Segment(1.0, 1.0, 2.0, 1.0, 0.2, "F.Cu", 1),
        Segment(2.0, 1.0, 4.0, 1.0, 0.2, "F.Cu", 1),
        Segment(1.0, 3.0, 2.0, 3.0, 0.2, "F.Cu", 2),
        Segment(2.0, 3.0, 4.0, 3.0, 0.2, "F.Cu", 2),
    ]
    pads = {
        1: [_pad("A", 1.0, 1.0, 1), _pad("B", 4.0, 1.0, 1)],
        2: [_pad("C", 1.0, 3.0, 2), _pad("D", 4.0, 3.0, 2)],
    }
    pcb = PCBData(
        BoardInfo({}, ["F.Cu"], (0.0, 0.0, 5.0, 4.0)),
        {1: Net(1, "N1"), 2: Net(2, "N2")}, {}, [], segments, pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu"], board_edge_clearance=0.0)

    outcome = run_post_smooth_gloss(
        [], pcb, config, GlossConfig(enable_multipasses=False), net_ids=[1])

    assert len([segment for segment in pcb.segments
                if segment.net_id == 1]) == 1
    assert len([segment for segment in pcb.segments
                if segment.net_id == 2]) == 2
    assert {segment.net_id for segment in
            outcome.input_strip_segments} == {1}


def test_g3_5_certifies_only_segments_present_in_the_final_board():
    pcb, config, first, _second = _parallel_board()
    removed_intermediate = Segment(
        2.0, 5.0, 2.01, 5.0, 0.2, "F.Cu", 1)
    changes = GlossChanges(segments=[
        {"old": first, "stage": "G3"},
        {"new": removed_intermediate, "stage": "G3"},
    ])
    context = build_gloss_context(pcb, config)
    grades = {net_id: _grade(pcb, net_id) for net_id in context.net_ids}

    assert math.isclose(
        _validate_final(context, grades,
                        calculate_route_length(pcb.segments), changes),
        calculate_route_length(pcb.segments), abs_tol=1e-12)

    preserved_micro = Segment(
        2.0, 5.0, 2.01, 5.0, 0.2, "F.Cu", 1)
    pcb.segments.append(preserved_micro)
    changes.segments.append({
        "new": preserved_micro, "stage": "G3.5",
        "geometry_preserving": True})
    assert math.isclose(
        _validate_final(context, grades,
                        calculate_route_length(pcb.segments), changes),
        calculate_route_length(pcb.segments), abs_tol=1e-12)


def test_g5_rejects_a_changed_pad_partition_even_if_connectivity_improves():
    pcb, config, _first, _second = _parallel_board()
    context = build_gloss_context(pcb, config, net_ids=[1])
    before = {
        "connected": False, "num_components": 2,
        "disconnected_pads": [(8.0, 5.0)],
        "pad_components": {("A",): 10, ("B",): 20},
    }
    after = {
        "connected": True, "num_components": 1,
        "disconnected_pads": [],
        "pad_components": {("A",): 30, ("B",): 30},
    }
    try:
        with patch("dgloss.pipeline._g5_grade", return_value=after):
            _certify_g5_copper(context, {1: before}, GlossChanges())
    except RuntimeError as exc:
        assert "topology changed" in str(exc)
    else:
        raise AssertionError("G5 accepted a changed pad partition")


def test_g5_rechecks_only_final_non_preserving_copper_with_krt():
    pcb, config, first, _second = _parallel_board()
    context = build_gloss_context(pcb, config, net_ids=[1])
    removed = Segment(2.0, 4.0, 8.0, 4.0, 0.2, "F.Cu", 1)
    preserving = Segment(2.0, 5.0, 8.0, 5.0, 0.2, "F.Cu", 1)
    pcb.segments.append(preserving)
    changes = GlossChanges(segments=[
        {"new": removed, "stage": "G3"},
        {"new": first, "stage": "G3"},
        {"new": preserving, "stage": "G3.5",
         "geometry_preserving": True},
    ])
    checked = []
    context.clearance_adapter.segment_clears = (
        lambda segment: checked.append(segment) or True)

    certified = _certify_g5_copper(
        context, {1: _g5_grade(pcb, 1)}, changes)

    assert checked == [first]
    assert certified == {
        "segments_certified": 1,
        "segments_geometry_preserved": 1,
        "vias_certified": 0,
    }


def test_g5_rejects_final_changed_copper_that_fails_krt_clearance():
    pcb, config, first, _second = _parallel_board()
    context = build_gloss_context(pcb, config, net_ids=[1])
    context.clearance_adapter.segment_clears = lambda _segment: False
    changes = GlossChanges(segments=[{"new": first, "stage": "G3"}])
    try:
        _certify_g5_copper(
            context, {1: _g5_grade(pcb, 1)}, changes)
    except RuntimeError as exc:
        assert "clearance regression" in str(exc)
    else:
        raise AssertionError("G5 accepted copper rejected by KRT")


def test_g5_rejects_changed_mobile_via_attributes():
    pcb, config, _first, _second = _parallel_board()
    old = Via(4.0, 5.0, 0.5, 0.2, ["F.Cu", "B.Cu"], 1)
    moved = Via(4.1, 5.0, 0.6, 0.2, ["F.Cu", "B.Cu"], 1)
    pcb.vias.append(moved)
    context = build_gloss_context(pcb, config, net_ids=[1])
    changes = GlossChanges(vias=[{"old": old, "new": moved, "stage": "G3.1"}])
    try:
        _certify_g5_copper(
            context, {1: _g5_grade(pcb, 1)}, changes)
    except RuntimeError as exc:
        assert "attributes changed" in str(exc)
    else:
        raise AssertionError("G5 accepted changed via attributes")


def test_g3_sliding_candidates_never_join_axes_at_90_degrees():
    families = list(_sliding_candidate_families(
        (1.0, 1.0), (6.0, 8.0), "F.Cu", 0.2, 1, 0.1))
    assert len(families) == 2
    for family in families:
        for candidate in family:
            for first, second in zip(candidate, candidate[1:]):
                ux = first.end_x - first.start_x
                uy = first.end_y - first.start_y
                vx = second.end_x - second.start_x
                vy = second.end_y - second.start_y
                assert not math.isclose(ux * vx + uy * vy, 0.0,
                                        abs_tol=1e-9)


def test_g3_rejects_new_90_degree_corner_at_candidate_boundary():
    points = [(0.0, 0.0), (0.0, 1.0), (3.0, 4.0),
              (4.0, 5.0), (8.0, 5.0)]
    segments = [Segment(*points[i], *points[i + 1], 0.2, "F.Cu", 1)
                for i in range(len(points) - 1)]
    chain = _Chain(segments, points, "F.Cu", 0.2)
    context = types.SimpleNamespace(
        coord=types.SimpleNamespace(grid_step=0.1),
        clearance_adapter=types.SimpleNamespace(
            connector_clears=lambda _segments: True))

    def only_bad_boundary_candidate(a, b, layer, width, net_id):
        if a == points[0] and b == points[3]:
            yield [Segment(0.0, 0.0, 4.0, 4.0, width, layer, net_id),
                   Segment(4.0, 4.0, 4.0, 5.0, width, layer, net_id)]

    with patch("dgloss.algorithm._candidate_segments",
               side_effect=only_bad_boundary_candidate), \
            patch("dgloss.algorithm._sliding_candidate_families",
                  return_value=[]), \
            patch("dgloss.algorithm._candidate_clears", return_value=True):
        replacement = _best_chain_replacement(
            context, chain, 1, None, segments, [])
    assert replacement is None


def test_locked_segment_is_unchanged():
    pcb, config, segments = _staircase_board()
    segments[0].locked = True
    before = list(pcb.segments)
    outcome = run_final_gloss([], pcb, config)
    assert pcb.segments == before
    assert outcome.stats["nets_changed"] == 0


def test_g3_keeps_via_position_and_contact_fixed():
    pcb, config, _segments = _staircase_board()
    via = Via(x=2.0, y=2.0, size=0.5, drill=0.2,
              layers=["F.Cu", "B.Cu"], net_id=1)
    pcb.vias.append(via)
    original = (via.x, via.y, via.size, via.drill, tuple(via.layers))
    run_final_gloss([], pcb, config)
    assert (via.x, via.y, via.size, via.drill, tuple(via.layers)) == original
    assert any((math.isclose(s.start_x, via.x) and math.isclose(s.start_y, via.y)) or
               (math.isclose(s.end_x, via.x) and math.isclose(s.end_y, via.y))
               for s in pcb.segments if s.net_id == 1)


def test_g3_1_moves_only_a_simple_two_layer_via_on_krt_grid():
    segments = [
        Segment(1.0, 1.0, 3.0, 1.0, 0.2, "F.Cu", 1),
        Segment(3.0, 1.0, 3.0, 4.0, 0.2, "B.Cu", 1),
    ]
    via = Via(3.0, 1.0, 0.5, 0.2, ["F.Cu", "B.Cu"], 1)
    pads = {1: [_pad("A", 1.0, 1.0, 1),
                _pad("B", 3.0, 4.0, 1, "B.Cu")]}
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 6.0, 6.0)),
        {1: Net(1, "VCC")}, {}, [via], segments, pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu", "B.Cu"], board_edge_clearance=0.0)

    before = calculate_route_length(segments)
    outcome = run_final_gloss([], pcb, config)
    moved = pcb.vias[0]
    after = calculate_route_length(pcb.segments)

    assert outcome.stats["vias_moved"] == 1
    assert after < before - config.grid_step
    assert (moved.x, moved.y) != (via.x, via.y)
    assert math.isclose(moved.x / config.grid_step,
                        round(moved.x / config.grid_step), abs_tol=1e-9)
    assert math.isclose(moved.y / config.grid_step,
                        round(moved.y / config.grid_step), abs_tol=1e-9)
    assert (moved.size, moved.drill, moved.layers, moved.net_id) == \
           (via.size, via.drill, via.layers, via.net_id)
    assert outcome.input_strip_vias == [via]
    assert any(change.get("stage") == "G3.1"
               for change in outcome.changes["vias"])


def test_g3_2_uses_the_native_pad_centre_as_fixed_terminal():
    segments = [
        Segment(1.4, 1.0, 2.0, 1.0, 0.2, "F.Cu", 1),
        Segment(2.0, 1.0, 2.0, 2.0, 0.2, "F.Cu", 1),
        Segment(2.0, 2.0, 4.0, 2.0, 0.2, "F.Cu", 1),
    ]
    pad = _pad("A", 1.0, 1.0, 1)
    pad.size_x = pad.size_y = 0.8
    via = Via(4.0, 2.0, 0.5, 0.2, ["F.Cu", "B.Cu"], 1,
              locked=True)
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 6.0, 4.0)),
        {1: Net(1, "VCC")}, {}, [via], segments, {1: [pad]})
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu", "B.Cu"], board_edge_clearance=0.0)
    context = build_gloss_context(pcb, config)
    before = calculate_route_length(pcb.segments)

    strips, added, changes, stats = optimize_pad_terminals(
        context, [])

    assert stats["pads_changed"] == 1
    assert calculate_route_length(pcb.segments) < before - config.grid_step
    assert any(pos in ((segment.start_x, segment.start_y),
                       (segment.end_x, segment.end_y))
               for segment in pcb.segments for pos in [(pad.global_x,
                                                         pad.global_y)])
    touching = [segment for segment in pcb.segments
                if (pad.global_x, pad.global_y) in
                ((segment.start_x, segment.start_y),
                 (segment.end_x, segment.end_y))]
    assert len(touching) == 1
    assert strips == segments and added
    assert all(change.get("stage") == "G3.2"
               for change in changes.segments)


def test_g3_3_slides_only_the_t_branch_and_keeps_rail_identity():
    rail_left = Segment(1.0, 2.0, 3.0, 2.0, 0.2, "F.Cu", 1)
    rail_right = Segment(3.0, 2.0, 7.0, 2.0, 0.2, "F.Cu", 1)
    branch = Segment(3.0, 2.0, 4.0, 1.0, 0.2, "F.Cu", 1)
    branch_tail = Segment(4.0, 1.0, 6.0, 1.0, 0.2, "F.Cu", 1)
    pads = {1: [_pad("L", 1.0, 2.0, 1),
                _pad("R", 7.0, 2.0, 1),
                _pad("B", 6.0, 1.0, 1)]}
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 8.0, 6.0)),
        {1: Net(1, "N1")}, {}, [],
        [rail_left, rail_right, branch, branch_tail], pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu", "B.Cu"], board_edge_clearance=0.0)
    context = build_gloss_context(pcb, config)

    strips, added, changes, stats = slide_t_nodes(context, [])

    assert stats["t_branches_slid"] == 1
    assert rail_left in pcb.segments and rail_right in pcb.segments
    assert id(rail_left) == id(pcb.segments[0])
    assert id(rail_right) == id(pcb.segments[1])
    assert branch not in pcb.segments and branch_tail not in pcb.segments
    assert strips == [branch, branch_tail]
    assert len(added) == 1
    moved = added[0]
    assert {(moved.start_x, moved.start_y),
            (moved.end_x, moved.end_y)} == {(6.0, 1.0), (6.0, 2.0)}
    rail_vector = (rail_right.end_x - rail_right.start_x,
                   rail_right.end_y - rail_right.start_y)
    branch_vector = (moved.end_x - moved.start_x,
                     moved.end_y - moved.start_y)
    assert rail_vector[0] * branch_vector[0] + \
           rail_vector[1] * branch_vector[1] == 0.0
    assert all(change.get("stage") == "G3.3"
               for change in changes.segments)


def test_g3_3_pad_or_via_at_node_has_priority_over_sliding():
    rails = [Segment(1.0, 2.0, 3.0, 2.0, 0.2, "F.Cu", 1),
             Segment(3.0, 2.0, 7.0, 2.0, 0.2, "F.Cu", 1)]
    branch = Segment(3.0, 2.0, 6.0, 5.0, 0.2, "F.Cu", 1)
    via = Via(3.0, 2.0, 0.5, 0.2, ["F.Cu", "B.Cu"], 1)
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 8.0, 6.0)),
        {1: Net(1, "N1")}, {}, [via], rails + [branch], {1: []})
    config = GridRouteConfig(clearance=0.1, grid_step=0.1,
                             layers=["F.Cu", "B.Cu"])
    context = build_gloss_context(pcb, config)

    _strips, _added, _changes, stats = slide_t_nodes(context, [])

    assert stats["t_branches_slid"] == 0
    assert pcb.segments == rails + [branch]


def test_g3_3_experiment_slides_noncollinear_t_and_cleans_old_right_angle():
    rail = Segment(3.0, 3.0, 7.0, 3.0, 0.2, "F.Cu", 1)
    residual = Segment(3.0, 3.0, 3.0, 7.0, 0.2, "F.Cu", 1)
    branch = Segment(3.0, 3.0, 4.0, 2.0, 0.2, "F.Cu", 1)
    tail = Segment(4.0, 2.0, 6.0, 2.0, 0.2, "F.Cu", 1)
    pads = {1: [_pad("R", 7.0, 3.0, 1),
                _pad("U", 3.0, 7.0, 1),
                _pad("B", 6.0, 2.0, 1)]}
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 9.0, 9.0)),
        {1: Net(1, "N1")}, {}, [], [rail, residual, branch, tail], pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu", "B.Cu"], board_edge_clearance=0.0)
    context = build_gloss_context(pcb, config)
    before = calculate_route_length(pcb.segments)

    strips, added, _changes, stats = slide_t_nodes(context, [])

    assert stats["noncollinear_t_slid"] == 1
    assert stats["right_angles_cleaned"] == 1
    assert calculate_route_length(pcb.segments) < before - config.grid_step
    assert branch in strips and tail in strips
    assert rail in strips and residual in strips
    assert added

    incidence = defaultdict(list)
    for segment in pcb.segments:
        for point in ((segment.start_x, segment.start_y),
                      (segment.end_x, segment.end_y)):
            other = ((segment.end_x, segment.end_y)
                     if point == (segment.start_x, segment.start_y)
                     else (segment.start_x, segment.start_y))
            incidence[pos_key(*point)].append(
                (other[0] - point[0], other[1] - point[1]))
    assert not any(len(vectors) == 2 and math.isclose(
        vectors[0][0] * vectors[1][0] +
        vectors[0][1] * vectors[1][1], 0.0, abs_tol=1e-9)
        for vectors in incidence.values())


def test_g3_3_noncollinear_t_variant_can_be_disabled():
    rail = Segment(3.0, 3.0, 7.0, 3.0, 0.2, "F.Cu", 1)
    residual = Segment(3.0, 3.0, 3.0, 7.0, 0.2, "F.Cu", 1)
    branch = Segment(3.0, 3.0, 4.0, 2.0, 0.2, "F.Cu", 1)
    tail = Segment(4.0, 2.0, 6.0, 2.0, 0.2, "F.Cu", 1)
    pads = {1: [_pad("R", 7.0, 3.0, 1),
                _pad("U", 3.0, 7.0, 1),
                _pad("B", 6.0, 2.0, 1)]}
    original = [rail, residual, branch, tail]
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 9.0, 9.0)),
        {1: Net(1, "N1")}, {}, [], list(original), pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu", "B.Cu"], board_edge_clearance=0.0)

    _strips, _added, _changes, stats = slide_t_nodes(
        build_gloss_context(pcb, config), [], allow_noncollinear=False)

    assert stats["noncollinear_t_slid"] == 0
    assert pcb.segments == original


def test_g3_4_optimizes_both_complete_portions_around_mobile_via():
    paths = [
        ([(1.0, 1.0), (3.0, 1.0), (4.0, 2.0), (4.0, 4.0)], "F.Cu"),
        ([(4.0, 4.0), (5.0, 5.0), (7.0, 5.0), (7.0, 8.0)], "B.Cu"),
    ]
    segments = [
        Segment(*vertices[index], *vertices[index + 1], 0.2, layer, 1)
        for vertices, layer in paths
        for index in range(len(vertices) - 1)
    ]
    via = Via(4.0, 4.0, 0.5, 0.2, ["F.Cu", "B.Cu"], 1,
              free=True, tenting_attrs={"tenting": "(front yes)"})
    pads = {1: [_pad("A", 1.0, 1.0, 1),
                _pad("B", 7.0, 8.0, 1, "B.Cu")]}
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 10.0, 10.0)),
        {1: Net(1, "N1")}, {}, [via], segments, pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu", "B.Cu"], board_edge_clearance=0.0)
    context = build_gloss_context(pcb, config)
    before = calculate_route_length(pcb.segments)

    _s1, _v1, _c1, g31 = move_mobile_vias(context, [])
    input_vias, emitted, changes, g34 = refine_mobile_vias(context, [])

    assert g31["vias_moved"] == 0
    assert g34["vias_moved"] == 1
    assert g34["saved_mm"] > config.grid_step
    assert calculate_route_length(pcb.segments) < before - config.grid_step
    assert input_vias == [via]
    assert {id(segment) for segment in g34["segment_strips"]} == \
           {id(segment) for segment in segments}
    assert len(emitted) == 1 and emitted[0] is pcb.vias[0]
    assert (emitted[0].size, emitted[0].drill, emitted[0].layers,
            emitted[0].net_id, emitted[0].free,
            emitted[0].tenting_attrs) == \
           (via.size, via.drill, via.layers, via.net_id, via.free,
            via.tenting_attrs)
    assert all(change.get("stage") == "G3.4"
               for change in changes.segments + changes.vias)


def test_g3_4_fixed_via_does_not_freeze_another_via_on_same_net():
    segments = [
        Segment(1.0, 1.0, 3.0, 1.0, 0.2, "F.Cu", 1),
        Segment(3.0, 1.0, 3.0, 4.0, 0.2, "B.Cu", 1),
        Segment(7.0, 8.0, 8.0, 8.0, 0.2, "F.Cu", 1),
        Segment(8.0, 8.0, 8.0, 9.0, 0.2, "B.Cu", 1),
    ]
    mobile = Via(3.0, 1.0, 0.5, 0.2, ["F.Cu", "B.Cu"], 1)
    fixed = Via(8.0, 8.0, 0.5, 0.2, ["F.Cu", "B.Cu"], 1,
                locked=True)
    pads = {1: [_pad("A", 1.0, 1.0, 1),
                _pad("B", 3.0, 4.0, 1, "B.Cu"),
                _pad("C", 7.0, 8.0, 1),
                _pad("D", 8.0, 9.0, 1, "B.Cu")]}
    pcb = PCBData(
        BoardInfo({}, ["F.Cu", "B.Cu"], (0.0, 0.0, 10.0, 10.0)),
        {1: Net(1, "N1")}, {}, [mobile, fixed], segments, pads)
    config = GridRouteConfig(
        track_width=0.2, clearance=0.1, grid_step=0.1,
        layers=["F.Cu", "B.Cu"], board_edge_clearance=0.0)
    context = build_gloss_context(pcb, config)

    _strips, emitted, _changes, stats = move_mobile_vias(context, [])

    assert stats["vias_moved"] == 1
    assert fixed in pcb.vias and (fixed.x, fixed.y) == (8.0, 8.0)
    assert len(emitted) == 1 and (emitted[0].x, emitted[0].y) != (3.0, 1.0)


def test_g3_comparison_uses_identical_input_and_reports_timing():
    pcb, config, _segments = _staircase_board()
    rows = compare_smoothers(pcb, config, net_ids=[1])
    assert len(rows) == 1
    row = rows[0]
    assert row["initial_mm"] > row["krt_final_mm"]
    assert row["initial_mm"] > row["dgloss_final_mm"]
    assert row["krt_valid"] and row["dgloss_valid"]
    assert row["dgloss_preparation_ms"] >= 0
    assert row["dgloss_ms"] >= 0
    table = format_comparison_table(rows)
    assert "KRT gain" in table and "dgloss gain" in table


def test_gloss_failure_restores_exact_krt_custody():
    pcb, config, first, _second = _parallel_board()
    results = [{"new_segments": [first], "new_vias": []}]
    board_ids = [id(s) for s in pcb.segments]
    result_ids = [id(s) for s in results[0]["new_segments"]]
    with patch("dgloss.pipeline.build_gloss_context",
               side_effect=RuntimeError("synthetic failure")):
        outcome = run_final_gloss(results, pcb, config)
    assert [id(s) for s in pcb.segments] == board_ids
    assert [id(s) for s in results[0]["new_segments"]] == result_ids
    assert len(results) == 1
    assert outcome.stats["gloss_errors"] == 1


def test_g1_is_lazy_and_dashes_old_copper():
    class UntouchedBoard:
        def __getattr__(self, name):
            raise AssertionError(f"empty visualisation touched board via {name}")

    assert add_changes_to_board(UntouchedBoard(), {"segments": [], "vias": []}) == 0
    parts = _line_parts((0.0, 0.0), (1.0, 0.0), dash=0.2, gap=0.1)
    assert len(parts) == 4
    assert parts[0] == ((0.0, 0.0), (0.2, 0.0))
    assert parts[-1][1][0] <= 1.0 + 1e-12


def test_g1_renames_a_free_layer_and_draws_changes():
    class Shape:
        def __init__(self, board):
            self.layer = None

        def SetShape(self, value): self.shape = value
        def SetStart(self, value): self.start = value
        def SetEnd(self, value): self.end = value
        def SetWidth(self, value): self.width = value
        def SetLayer(self, value): self.layer = value
        def GetLayer(self): return self.layer

    fake = types.ModuleType("pcbnew")
    for i in range(1, 10):
        setattr(fake, f"User_{i}", i)
    fake.PCB_SHAPE = Shape
    fake.SHAPE_T_SEGMENT = 1
    fake.VECTOR2I = lambda x, y: (x, y)

    class Board:
        def __init__(self):
            self.names = {i: f"User.{i}" for i in range(1, 10)}
            self.drawings = []
            self.modified = False

        def GetLayerName(self, layer): return self.names[layer]
        def SetLayerName(self, layer, name): self.names[layer] = name
        def GetEnabledLayers(self): return self
        def Contains(self, layer): return layer == fake.User_1
        def GetDrawings(self): return self.drawings
        def Add(self, item): self.drawings.append(item)
        def RemoveNative(self, item): self.drawings.remove(item)
        def SetModified(self): self.modified = True

    old = Segment(1.0, 1.0, 2.0, 1.0, 0.2, "F.Cu", 1)
    new = Segment(1.0, 1.0, 2.0, 1.0, 0.6, "F.Cu", 1)
    board = Board()
    with patch.dict(sys.modules, {"pcbnew": fake}):
        count = add_changes_to_board(
            board, {"segments": [{"old": old, "new": new}], "vias": []})
    assert count == len(board.drawings) and count > 1
    assert board.names[fake.User_1] == "TrackGloss G3"
    assert board.modified


def test_add_layer_user_enables_missing_user1_without_overwriting_content():
    class LayerSet:
        def __init__(self): self.layers = set()
        def Contains(self, layer): return layer in self.layers
        def AddLayer(self, layer): self.layers.add(layer)

    fake = types.SimpleNamespace(User_1=101)

    class Board:
        def __init__(self):
            self.enabled = LayerSet()
            self.visible = LayerSet()
            self.names = {101: "User.1"}
            self.count = 0
        def GetDrawings(self): return []
        def GetLayerName(self, layer): return self.names[layer]
        def SetLayerName(self, layer, name): self.names[layer] = name
        def GetUserDefinedLayerCount(self): return self.count
        def SetUserDefinedLayerCount(self, count): self.count = count
        def GetEnabledLayers(self): return self.enabled
        def SetEnabledLayers(self, layers): self.enabled = layers
        def GetVisibleLayers(self): return self.visible
        def SetVisibleLayers(self, layers): self.visible = layers

    board = Board()
    assert add_layer_user(board, fake, "G3") == 101
    assert board.count == 1
    assert board.enabled.Contains(101) and board.visible.Contains(101)
    assert board.names[101] == "TrackGloss G3"


def test_g4_disables_owned_intermediate_layers_without_deleting_drawings():
    class LayerSet:
        def __init__(self, layers): self.layers = set(layers)
        def Contains(self, layer): return layer in self.layers
        def RemoveLayer(self, layer): self.layers.remove(layer)

    fake = types.SimpleNamespace(**{f"User_{i}": i for i in range(1, 7)})

    class Board:
        def __init__(self):
            self.enabled = LayerSet(range(1, 7))
            self.visible = LayerSet(range(1, 7))
            self.names = {
                1: "TrackGloss Changes", 2: "TrackGloss G3.1",
                3: "TrackGloss G3.2", 4: "User notes",
                5: "TrackGloss G3.4", 6: "TrackGloss G3.5",
            }
            self.drawings = [object(), object()]
        def GetLayerName(self, layer): return self.names[layer]
        def GetEnabledLayers(self): return self.enabled
        def SetEnabledLayers(self, layers): self.enabled = layers
        def GetVisibleLayers(self): return self.visible
        def SetVisibleLayers(self, layers): self.visible = layers

    board = Board()
    before = list(board.drawings)
    disable_intermediate_layers(board, fake)
    assert board.enabled.layers == {1, 4}
    assert board.visible.layers == {1, 4}
    assert board.drawings == before


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        print(test.__name__)
        test()
        print("  PASS")
    print("ALL PASS")
