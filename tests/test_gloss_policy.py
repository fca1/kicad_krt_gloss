"""Fast checks for the shared Gloss policy and transaction boundaries."""

from types import SimpleNamespace
from time import perf_counter
from unittest.mock import Mock

import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime

configure_krt_runtime()

from routing_config import GridRouteConfig
from kicad_parser import Segment
from dgloss import GlossConfig
from dgloss import pipeline, context as context_module
from dgloss.algorithm import _adaptive_chamfer_candidates, _candidate_clearance
from dgloss.changes import GlossChanges
from dgloss.passes import _collect, run_multinet_passes


def test_via_permission_disables_both_searches(monkeypatch):
    pcb = SimpleNamespace(segments=[], vias=[], pads_by_net={})
    context = SimpleNamespace(pcb_data=pcb, net_ids=[], branch_scoped=False)
    local = Mock(side_effect=AssertionError("local via search must not run"))
    full = Mock(side_effect=AssertionError("full via search must not run"))
    monkeypatch.setattr(pipeline, "move_mobile_vias", local)
    monkeypatch.setattr(pipeline, "refine_mobile_vias", full)
    monkeypatch.setattr(pipeline, "merge_collinear_segments",
                        lambda *a, **k: (0, 0, [], [], {}))
    for selected in (GlossConfig(move_vias=False), GlossConfig(enable_g3_1=False)):
        pipeline._run_optimization_pass([], context, selected, [],
                                        perf_counter() + 1, emit_log=False)
    local.assert_not_called()
    full.assert_not_called()


def test_shared_entry_restores_input_on_failure(monkeypatch):
    original = Segment(0, 0, 1, 0, .2, "F.Cu", 1)
    pcb = SimpleNamespace(segments=[original], vias=[])
    results = [{"new_segments": [original], "new_vias": []}]
    monkeypatch.setattr(pipeline, "resolve_gloss_scope", lambda *a: ([1], set(), {}))
    monkeypatch.setattr(pipeline, "build_gloss_context", lambda *a, **k:
                        SimpleNamespace(pcb_data=pcb, net_ids=[1]))
    monkeypatch.setattr(pipeline, "_grade", lambda *a: {})
    monkeypatch.setattr(pipeline, "_g5_grade", lambda *a: {})

    def fail(*a, **k):
        pcb.segments = []
        results[0]["new_segments"] = []
        results.append({"new_segments": [], "new_vias": []})
        raise RuntimeError("injected failure")

    monkeypatch.setattr(pipeline, "_run_optimization_pass", fail)
    outcome = pipeline.run_final_gloss(results, pcb, GridRouteConfig(), net_ids=[1])
    assert outcome.stats["gloss_errors"] == 1
    assert pcb.segments == [original]
    assert results == [{"new_segments": [original], "new_vias": []}]


def test_layers_limit_editing_without_hiding_obstacles(monkeypatch):
    front = Segment(0, 0, 1, 0, .2, "F.Cu", 1)
    back = Segment(0, 0, 1, 0, .2, "B.Cu", 1)
    pcb = SimpleNamespace(segments=[front, back],
                          board_info=SimpleNamespace(copper_layers=["F.Cu", "B.Cu"]))
    for name in ("build_base_obstacle_map", "precompute_all_net_obstacles",
                 "build_working_obstacle_map", "KrtClearanceAdapter"):
        monkeypatch.setattr(context_module, name, lambda *a, **k: {})
    context = context_module.build_gloss_context(
        pcb, GridRouteConfig(layers=["F.Cu"]), [1])
    assert context.segments_editable([front])
    assert not context.segments_editable([back])
    assert context.config.layers == ["F.Cu", "B.Cu"]
    context = context_module.build_gloss_context(
        pcb, GridRouteConfig(layers=["F.Cu"]), [1],
        editable_segment_ids={id(back)})
    assert context.editable_segment_ids == set()


def test_expired_chamfer_search_does_no_work():
    assert list(_adaptive_chamfer_candidates(
        None, None, (0, 0), (10, 10), "F.Cu", .2, 1, 25, deadline=0)) == []


def test_candidate_origin_does_not_change_exact_clearance():
    segment = Segment(0, 0, 1, 0, .2, "F.Cu", 1)
    context = SimpleNamespace(coord=SimpleNamespace(grid_step=.1),
                              clearance_adapter=SimpleNamespace(
                                  connector_clears=lambda segments: True))
    for source in ("canonical", "chamfer"):
        assert _candidate_clearance(context, None, [segment], source)


def test_pass_history_keeps_origin_without_mutating_source():
    entry = {"stage": "G3.2", "new": object()}
    target = GlossChanges()
    _collect(target, {"segments": [entry]}, pass_index=3)
    assert target.segments[0]["stage"] == "G3.2"
    assert target.segments[0]["pass_index"] == 3
    assert "pass_index" not in entry


def test_operation_totals_include_later_passes():
    context = SimpleNamespace(pcb_data=SimpleNamespace(segments=[]), net_ids=[1])
    counts = iter((2, 0))

    def run(*args, **kwargs):
        count = next(counts)
        return {
            "changes": GlossChanges(), "segment_strips": [], "via_strips": [],
            "stage_stats": SimpleNamespace(as_dict=lambda: {
                "stages": {"via": {"changes": count}}}),
            "changed_net_ids": {1} if count else set(),
            "g3": {}, "via": {"vias_moved": count}, "pad": {},
            "node": {}, "refine": {}, "merge": {},
            "equal": {"segments_removed": 0, "segments_added": 0},
            "merged_count": 0, "merged_nets": 0, "merge_ms": 0,
        }

    outcome = run_multinet_passes(context, GlossConfig(), [1], [],
                                  perf_counter() + 1, run)
    assert outcome["operation_totals"]["via"]["vias_moved"] == 2
    assert outcome["passes_completed"] == 2
    assert outcome["passes"][0]["operations"]["via"]["changes"] == 2


@pytest.mark.parametrize("budget", [-1, float("inf"), float("nan")])
def test_invalid_budget_is_rejected(budget):
    with pytest.raises(ValueError):
        GlossConfig(budget_seconds=budget)


def test_local_partition_rejects_split_even_when_counts_do_not_change():
    from dgloss.algorithm import _connectivity_worse
    from dgloss.topology import terminal_partition

    def grade(edges):
        return {"connected": False, "num_components": 2,
                "disconnected_pads": [0, 1], "graph": {
                    "edges": edges, "pad_index_repr": {0: "a", 1: "b", 2: "c"},
                    "zone_index_repr": {0: "z"}}}

    before = grade([("a", "b"), ("c", "z")])
    after = grade([("a", "z"), ("b", "c")])
    assert _connectivity_worse(before, after)
    assert terminal_partition(before) == pipeline._terminal_partition(before)
    assert not _connectivity_worse(before, before)


def test_local_certificate_includes_zone_and_builds_baseline_once(monkeypatch):
    from dgloss import topology

    source = Segment(0, 0, 1, 0, .2, "F.Cu", 1)
    zone = SimpleNamespace(net_id=1)
    foreign = SimpleNamespace(net_id=2)
    pcb = SimpleNamespace(zones=[zone, foreign], pads_by_net={1: []})
    check = Mock(return_value={"graph": {"edges": [], "pad_index_repr": {}}})
    monkeypatch.setattr(topology, "_check", check)
    guard = topology.ReplacementGuard(pcb, 1, [source], [])
    assert check.call_count == 0
    assert guard([source], [source])
    assert guard([source], [source])
    assert check.call_count == 2  # baseline + candidate, no duplicate certificate
    assert guard([source], [])
    assert check.call_count == 3
    assert all(call.args[4] == [zone] and call.kwargs["return_graph"]
               for call in check.call_args_list)


def test_pad_search_retries_after_electrical_rejection(monkeypatch):
    from dgloss import pad_terminals

    short = [Segment(0, 0, 5, 5, .2, "F.Cu", 1)]
    next_best = [Segment(0, 0, 1, 0, .2, "F.Cu", 1),
                 Segment(1, 0, 5, 4, .2, "F.Cu", 1),
                 Segment(5, 4, 5, 5, .2, "F.Cu", 1)]
    chain = [Segment(0, 0, 0, 5, .2, "F.Cu", 1),
             Segment(0, 5, 5, 5, .2, "F.Cu", 1)]
    monkeypatch.setattr(pad_terminals, "_connector_families", lambda *a:
                        [("canonical", [short, next_best])])
    context = SimpleNamespace(coord=SimpleNamespace(grid_step=.1),
                              clearance_adapter=SimpleNamespace(
                                  connector_clears=lambda segments: True))
    accept = Mock(side_effect=lambda removed, added: added is next_best)
    result = pad_terminals._best_pad_connector(
        context, SimpleNamespace(global_x=0, global_y=0), chain,
        [(0, 0), (0, 5), (5, 5)], [], [], None, accept_replacement=accept)
    assert result is next_best
    assert accept.call_count == 2


def test_pad_distance_cache_never_caches_movable_copper(monkeypatch):
    from dgloss import krt_clearance
    from functools import lru_cache

    adapter = krt_clearance.KrtClearanceAdapter.__new__(krt_clearance.KrtClearanceAdapter)
    adapter.pcb = object()
    adapter.config = SimpleNamespace()
    adapter.clearance = adapter.npth_clearance = .2
    adapter.net_clearances = adapter.track_clearances = None
    adapter._edge_clears = adapter._keepouts_clear = lambda segment: True
    pads = Mock(return_value=1)
    moving = Mock(side_effect=[1, 0])
    monkeypatch.setattr(krt_clearance, "foreign_pad_clearance_distance", pads)
    monkeypatch.setattr(krt_clearance, "_exact_foreign_segment_distance", moving)
    monkeypatch.setattr(krt_clearance, "_exact_foreign_hole_distance", lambda *a: 1)
    adapter._pad_distance = lru_cache(maxsize=8192)(adapter._uncached_pad_distance)
    segment = Segment(0, 0, 1, 0, .2, "F.Cu", 1)
    assert adapter.segment_clears(segment)
    assert not adapter.segment_clears(segment)
    assert pads.call_count == 1
    assert moving.call_count == 2


def test_chain_search_retries_an_unsafe_combination(monkeypatch):
    from dgloss import algorithm

    points = [(0, 0), (0, 2), (2, 2), (2, 4), (4, 4)]
    segments = algorithm._segments_for_points(points, "F.Cu", .2, 1)
    chain = algorithm._Chain(segments, points, "F.Cu", .2)
    context = SimpleNamespace(coord=SimpleNamespace(grid_step=.1),
                              clearance_adapter=SimpleNamespace(
                                  connector_clears=lambda segments: True))
    monkeypatch.setattr(algorithm, "_adaptive_chamfer_candidates", lambda *a: [])
    monkeypatch.setattr(algorithm, "_reachable_segment_slides", lambda *a, **k: [])
    calls = []

    def accept(removed, added):
        calls.append(len(removed))
        return len(removed) == 2

    result = algorithm._best_chain_replacement(
        context, chain, 1, None, segments, [],
        deadline=perf_counter() + 1, accept_replacement=accept)
    assert result is not None
    assert len(result[0]) == 2
    assert 4 in calls and 2 in calls


def test_krt_arrays_reused_only_inside_read_only_search(monkeypatch):
    import numpy as np
    from dgloss import krt_clearance

    adapter = krt_clearance.KrtClearanceAdapter.__new__(krt_clearance.KrtClearanceAdapter)
    adapter.pcb = SimpleNamespace(segments=[], vias=[])
    adapter._copper_batch = None
    adapter.copper_data_stats = {"builds": 0, "reuses": 0}
    arrays = tuple(np.array([x]) for x in (2, 0., 0., 1., 1., .1))
    source = Mock(return_value=arrays)
    monkeypatch.setattr(krt_clearance, "_foreign_seg_arrays", source)
    assert adapter._prepared_copper("F.Cu") is None
    with pytest.raises(RuntimeError):
        with adapter.stable_copper():
            first = adapter._prepared_copper("F.Cu")
            with adapter.stable_copper():
                assert adapter._prepared_copper("F.Cu") is first
            raise RuntimeError("interrupted search")
    assert adapter._prepared_copper("F.Cu") is None
    adapter.pcb.segments = [object()]  # a committed change between searches
    with adapter.stable_copper():
        assert adapter._prepared_copper("F.Cu") is not first
    assert source.call_count == 2
    assert adapter.copper_data_stats == {"builds": 2, "reuses": 1}
