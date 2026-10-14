"""Elementary-branch discovery and scope bookkeeping."""

from pathlib import Path
import sys
import pytest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
KRT_ROUTER = ROOT / "KRT" / "py_router"
sys.path[:0] = [str(ROOT), str(KRT_ROUTER)]

from kicad_parser import Segment, Via

from dgloss.branches import elementary_branch_segment_ids
from dgloss.context import GlossContext
from dgloss.pipeline import _merge_collinear_in_scope


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


@pytest.mark.parametrize('angle', [0, 45, 90])
@pytest.mark.parametrize('reflection', [-1, 1])
def test_pad_touching_only_wide_side_stops_both_directions(angle, reflection):
    from itertools import permutations
    from math import cos, sin, radians
    def transform(x, y):
        c, s = cos(radians(angle)), sin(radians(angle))
        return c*x - s*y*reflection, s*x + c*y*reflection
    narrow = _seg(0, 0, 1, 0, width=0.1)
    wide = _seg(1, 0, 2, 0, width=0.4)
    for segment in (narrow, wide):
        segment.start_x, segment.start_y = transform(segment.start_x, segment.start_y)
        segment.end_x, segment.end_y = transform(segment.end_x, segment.end_y)
    px, py = transform(1., .25)
    pad = SimpleNamespace(
        global_x=px, global_y=py, size_x=0.2, size_y=0.2,
        shape="rect", layers=["F.Cu"], rect_rotation=angle,
        polygons=None, net_id=1)
    pcb = _pcb([narrow, wide], pads=[pad])
    for seed in (narrow, wide):
        assert elementary_branch_segment_ids(pcb, [seed]) == ({id(seed)}, 1)
    for seeds in permutations([narrow, wide]):
        assert elementary_branch_segment_ids(pcb, seeds) == (
            {id(narrow), id(wide)}, 2)


def test_pad_on_other_side_of_via_stops_both_directions():
    front = _seg(0, 0, 1, 0)
    back = _seg(1, 0, 2, 0, layer="B.Cu")
    via = Via(1, 0, 0.5, 0.25, ["F.Cu", "B.Cu"], 1)
    pad = SimpleNamespace(
        global_x=1.0, global_y=0.0, size_x=0.4, size_y=0.4,
        shape="rect", layers=["B.Cu"], rect_rotation=0.0,
        polygons=None, net_id=1)
    pcb = _pcb([front, back], pads=[pad], vias=[via])
    for seed in (front, back):
        assert elementary_branch_segment_ids(pcb, [seed]) == ({id(seed)}, 1)


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


def test_scoped_merge_exposes_only_branch_copper_as_mutable():
    editable = _seg(0, 0, 1, 0)
    editable_tail = _seg(1, 0, 2, 0)
    outside = _seg(2, 0, 3, 0)
    replacement = _seg(0, 0, 2, 0)
    pcb = _pcb([editable, editable_tail, outside])
    results = [{"new_segments": [editable, editable_tail, outside], "new_vias": []}]

    def fake_smooth(scratch, live_pcb, net_ids, **kwargs):
        assert scratch[0]["new_segments"] == [editable, editable_tail]
        assert kwargs["keep_input_copper"] is True
        assert set(net_ids) == {1}
        live_pcb.segments = [outside, replacement]
        return 1, 1, [], [replacement], {"spans": 1}

    context = GlossContext(
        pcb_data=pcb, config=None, coord=None, layer_map={}, net_ids=[1],
        working_obstacles=None, net_obstacles={}, clearance_adapter=None,
        excluded_net_ids=set(), exclusion_reasons={},
        editable_segment_ids={id(editable), id(editable_tail)})
    with patch("dgloss.pipeline.merge_collinear_segments", fake_smooth):
        changed, nets, native, added, stats = \
            _merge_collinear_in_scope(results, context, [1])

    assert (changed, nets, native, added) == (1, 1, [], [replacement])
    assert stats['spans'] == 1 and stats['rejections'] == []
    assert pcb.segments == [outside, replacement]
    assert results[0]["new_segments"] == [outside]
    assert results[1]["new_segments"] == [replacement]
    assert context.editable_segment_ids == {id(replacement)}
