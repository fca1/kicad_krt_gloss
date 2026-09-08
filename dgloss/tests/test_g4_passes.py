from types import SimpleNamespace
import pytest

from dgloss import GlossConfig
from dgloss.passes import run_multinet_passes


class _Board:
    segments = []


@pytest.mark.parametrize('initial,gains,limit,threshold,expected,count', [
    (20., [10., 1., 5.], 5, 10., 'marginal_gain', 2),
    (20., [10., 1.001, 5.], 2, 10., 'max_passes', 2),
    (20., [10., 1., .01], 5, 5., 'marginal_gain', 3),
    (0., [0., 0., 0.], 2, 10., 'max_passes', 2),
    (20., [10.], 0, 10., 'max_passes', 0),
    (100., [10., 5.], 2, 10., 'marginal_gain', 1),
    (100., [9., 5.], 2, 10., 'marginal_gain', 1),
    (100., [10.001, 5.], 2, 10., 'max_passes', 2),
])
def test_g4_limits_and_unrounded_gain_with_expired_initial_budget(
        monkeypatch, initial, gains, limit, threshold, expected, count):
    length = [100.]
    calls = []
    monkeypatch.setitem(run_multinet_passes.__globals__, 'calculate_route_length',
                        lambda _: length[0])
    def run(results, context, config, net_ids, deadline, *, emit_log):
        assert deadline == float('inf')
        length[0] -= gains[len(calls)]
        calls.append(net_ids)
        return dict(
            segment_strips=[], via_strips=[],
            changes=SimpleNamespace(as_dict=lambda: dict(segments=[], vias=[])),
            stage_stats=SimpleNamespace(as_dict=lambda: {'stages': {'G3': {'changes': 1}}}),
            changed_net_ids={1}, g3={}, via={}, pad={}, node={}, refine={}, merge={},
            merged_nets=0, merge_ms=0, merged_count=0,
            equal=dict(segments_removed=0, segments_added=0))
    out = run_multinet_passes(
        SimpleNamespace(pcb_data=_Board(), net_ids=[1]),
        GlossConfig(g4_max_passes=limit, g4_min_gain_percent=threshold),
        [1], [], 0., run, initial_gain=initial)
    assert out['stop_reason'] == expected
    assert out['passes_completed'] == count


@pytest.mark.parametrize('values', [
    {'g4_max_passes': -1}, {'g4_max_passes': 1.5}, {'g4_max_passes': True},
    {'g4_min_gain_percent': -1}, {'g4_min_gain_percent': 101},
    {'g4_min_gain_percent': float('nan')},
])
def test_invalid_g4_limits(values):
    with pytest.raises(ValueError):
        GlossConfig(**values)


def test_g4_replays_g3_5_in_alternating_complete_net_orders():
    calls = []

    def run_g3_5(results, context, gloss_config, net_ids, deadline, *, emit_log):
        calls.append((list(net_ids), gloss_config.enable_multipasses))
        assert emit_log is False
        changed = len(calls) == 1
        return {
            "segment_strips": [], "via_strips": [],
            "changes": SimpleNamespace(
                as_dict=lambda: {"segments": [], "vias": []}),
            "stage_stats": SimpleNamespace(as_dict=lambda: {
                "stages": {"G3": {"changes": int(changed)}}}),
            "changed_net_ids": set(net_ids) if changed else set(),
            "g3": {}, "via": {}, "pad": {}, "node": {},
            "refine": {}, "merge": {}, "merged_nets": 0, "merge_ms": 0,
            "equal": {"segments_removed": int(changed),
                      "segments_added": 0},
            "merged_count": 0,
        }

    context = SimpleNamespace(pcb_data=_Board(), net_ids=[1, 2])
    outcome = run_multinet_passes(
        context, GlossConfig(), [2, 1], [],
        float("inf"), run_g3_5)

    assert calls == [([1, 2], True), ([2, 1], True)]
    assert [row["direction"] for row in outcome["passes"]] == [
        "forward", "reverse"]
    assert outcome["stop_reason"] == "converged"
    assert outcome["segment_reduction"] == 1
    assert [row["segment_reduction"] for row in outcome["passes"]] == [1, 0]


def test_g4_propagates_an_internal_g3_5_failure_to_g0():
    def failing_g3_5(*_args, **_kwargs):
        raise RuntimeError("synthetic G3.5 failure")

    try:
        context = SimpleNamespace(pcb_data=_Board(), net_ids=[1])
        run_multinet_passes(
            context, GlossConfig(), [1], [],
            float("inf"), failing_g3_5)
    except RuntimeError as exc:
        assert "synthetic G3.5 failure" in str(exc)
    else:
        raise AssertionError("G4 swallowed an internal G3.5 failure")
