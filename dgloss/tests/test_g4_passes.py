from types import SimpleNamespace

from dgloss import GlossConfig
from dgloss.passes import run_multinet_passes


class _Board:
    segments = []


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
