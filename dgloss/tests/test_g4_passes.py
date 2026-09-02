from types import SimpleNamespace

from dgloss import GlossConfig
from dgloss.passes import run_multinet_passes


class _Board:
    segments = []


def test_g4_replays_g3_5_in_alternating_complete_net_orders():
    calls = []

    def run_g3_5(results, pcb_data, config, gloss_config, net_ids,
                 deadline, *, emit_log):
        calls.append((net_ids[0], gloss_config.enable_multipasses))
        assert emit_log is False
        changed = len(calls) <= 2
        return {
            "segment_strips": [], "via_strips": [],
            "changes": SimpleNamespace(
                as_dict=lambda: {"segments": [], "vias": []}),
            "stage_stats": SimpleNamespace(as_dict=lambda: {
                "stages": {"G3": {"changes": int(changed)}}}),
            "changed_net_ids": {net_ids[0]} if changed else set(),
            "equal": {"segments_removed": int(changed),
                      "segments_added": 0},
            "merged_count": 0,
        }

    outcome = run_multinet_passes(
        _Board(), object(), GlossConfig(), [2, 1], [],
        float("inf"), run_g3_5)

    assert calls == [(1, False), (2, False), (2, False), (1, False)]
    assert [row["direction"] for row in outcome["passes"]] == [
        "forward", "reverse"]
    assert outcome["stop_reason"] == "converged"
    assert outcome["segment_reduction"] == 2
    assert [row["segment_reduction"] for row in outcome["passes"]] == [2, 0]


def test_g4_propagates_an_internal_g3_5_failure_to_g0():
    def failing_g3_5(*_args, **_kwargs):
        raise RuntimeError("synthetic G3.5 failure")

    try:
        run_multinet_passes(
            _Board(), object(), GlossConfig(), [1], [],
            float("inf"), failing_g3_5)
    except RuntimeError as exc:
        assert "synthetic G3.5 failure" in str(exc)
    else:
        raise AssertionError("G4 swallowed an internal G3.5 failure")
