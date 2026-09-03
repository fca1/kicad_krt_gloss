"""Elementary-branch discovery and scope bookkeeping."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
KRT_ROUTER = ROOT / "KRT" / "py_router"
sys.path[:0] = [str(ROOT), str(KRT_ROUTER)]

from kicad_parser import Segment, Via

from dgloss.branches import elementary_branch_segment_ids
from dgloss.context import GlossContext
from dgloss.pipeline import _run_scoped_krt_smooth


def _pcb(segments, *, vias=(), pads=()):
    return SimpleNamespace(
        segments=list(segments), vias=list(vias), pads_by_net={1: list(pads)},
        board_info=SimpleNamespace(copper_layers=["F.Cu", "In1.Cu", "B.Cu"]))


def _seg(ax, ay, bx, by, *, layer="F.Cu", width=0.2):
    return Segment(ax, ay, bx, by, width, layer, 1)


def test_t_junction_stops_the_branch_but_keeps_the_seed_side_complete():
    left = _seg(0, 0, 1, 0)
    right = _seg(1, 0, 2, 0)
    branch = _seg(1, 0, 1, 1)
    tail = _seg(1, 1, 1, 2)

    selected, count = elementary_branch_segment_ids(
        _pcb([left, right, branch, tail]), [branch])

    assert selected == {id(branch), id(tail)}
    assert count == 1


def test_width_change_remains_inside_one_elementary_branch():
    narrow = _seg(0, 0, 1, 0, width=0.2)
    wide = _seg(1, 0, 2, 0, width=0.4)

    selected, count = elementary_branch_segment_ids(
        _pcb([narrow, wide]), [narrow])

    assert selected == {id(narrow), id(wide)}
    assert count == 1


def test_same_net_via_connects_the_branch_across_its_spanned_layers():
    front = _seg(0, 0, 1, 0)
    back = _seg(1, 0, 2, 0, layer="B.Cu")
    via = Via(1, 0, 0.5, 0.25, ["F.Cu", "B.Cu"], 1)

    selected, count = elementary_branch_segment_ids(
        _pcb([front, back], vias=[via]), [front])

    assert selected == {id(front), id(back)}
    assert count == 1


def test_blind_via_does_not_join_a_layer_outside_its_span():
    front = _seg(0, 0, 1, 0)
    back = _seg(1, 0, 2, 0, layer="B.Cu")
    via = Via(1, 0, 0.5, 0.25, ["F.Cu", "In1.Cu"], 1)

    selected, count = elementary_branch_segment_ids(
        _pcb([front, back], vias=[via]), [front])

    assert selected == {id(front)}
    assert count == 1


def test_pad_landing_stops_the_branch_walk():
    first = _seg(0, 0, 1, 0)
    second = _seg(1, 0, 2, 0)
    pad = SimpleNamespace(
        global_x=1.0, global_y=0.0, size_x=0.4, size_y=0.4,
        shape="rect", layers=["F.Cu"], rect_rotation=0.0,
        polygons=None, net_id=1)

    selected, count = elementary_branch_segment_ids(
        _pcb([first, second], pads=[pad]), [first])

    assert selected == {id(first)}
    assert count == 1


def test_two_seeds_on_the_same_branch_are_counted_once():
    first = _seg(0, 0, 1, 0)
    second = _seg(1, 0, 2, 0)

    selected, count = elementary_branch_segment_ids(
        _pcb([first, second]), [first, second])

    assert selected == {id(first), id(second)}
    assert count == 1


def test_context_transports_editability_through_replacements():
    old = _seg(0, 0, 1, 0)
    outside = _seg(2, 0, 3, 0)
    new = _seg(0, 0, 1, 1)
    context = GlossContext(
        pcb_data=None, config=None, coord=None, layer_map={}, net_ids=[1],
        working_obstacles=None, net_obstacles={}, clearance_adapter=None,
        excluded_net_ids=set(), exclusion_reasons={},
        editable_segment_ids={id(old)})

    assert context.segments_editable([old])
    assert not context.segments_editable([old, outside])
    context.replace_editable_segments([old], [new])
    assert context.editable_segment_ids == {id(new)}


def test_scoped_krt_smooth_exposes_only_branch_copper_as_mutable():
    editable = _seg(0, 0, 1, 0)
    outside = _seg(1, 0, 2, 0)
    replacement = _seg(0, 0, 1, 1)
    pcb = SimpleNamespace(segments=[editable, outside], vias=[])
    results = [{"new_segments": [editable, outside], "new_vias": []}]

    def fake_smooth(scratch, live_pcb, net_ids, **kwargs):
        assert scratch[0]["new_segments"] == [editable]
        assert kwargs["keep_input_copper"] is True
        assert net_ids == [1]
        live_pcb.segments = [outside, replacement]
        return 1, 1, [], [replacement], {"spans": 1}

    with patch("dgloss.pipeline.smooth_octolinear_chains", fake_smooth):
        changed, nets, native, added, stats, updated = \
            _run_scoped_krt_smooth(
                results, pcb, [1], {id(editable)}, min_gain=0.1)

    assert (changed, nets, native, added, stats) == \
        (1, 1, [], [replacement], {"spans": 1})
    assert pcb.segments == [outside, replacement]
    assert results[0]["new_segments"] == [outside]
    assert results[1]["new_segments"] == [replacement]
    assert updated == {id(replacement)}
