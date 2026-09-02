from types import SimpleNamespace

from dgloss import GlossConfig
from dgloss.passes import run_multinet_passes


class _Board:
    segments = []


def test_g4_replays_g3_5_in_alternating_complete_net_orders():
    calls = []

    def run_g3_5(results, pcb_data, config, gloss_config, *, net_ids,
                 _emit_log, _run_g5):
        calls.append((net_ids[0], gloss_config.enable_multipasses))
        assert _emit_log is False
        assert _run_g5 is False
        changed = len(calls) <= 2
        return SimpleNamespace(
            input_strip_segments=[], input_strip_vias=[],
            changes={"segments": [], "vias": []},
            stats={"segment_changes": int(changed), "via_changes": 0,
                   "nets_changed": int(changed),
                   "equal_length_segment_reduction": int(changed),
                   "segments_merged": 0})

    outcome = run_multinet_passes(
        _Board(), object(), GlossConfig(), [2, 1], [],
        float("inf"), run_g3_5)

    assert calls == [(1, False), (2, False), (2, False), (1, False)]
    assert [row["direction"] for row in outcome["passes"]] == [
        "forward", "reverse"]
    assert outcome["stop_reason"] == "converged"
    assert outcome["segment_reduction"] == 2
    assert [row["segment_reduction"] for row in outcome["passes"]] == [2, 0]
