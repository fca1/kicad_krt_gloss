"""A KRT merge label does not replace proof of physical support preservation."""
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss.krt_merge import same_copper_support
from dgloss.krt_api import Segment
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def seg(a, b, width=.2):
    return Segment(*a, *b, width, 'F.Cu', 1)


def test_real_collinear_union_is_preserved_in_both_directions():
    source = [seg((0, 0), (1, 1)), seg((1, 1), (2, 2))]
    assert same_copper_support(source, [seg((2, 2), (0, 0))])


def test_micron_adjacency_does_not_allow_closing_a_physical_gap():
    source = [seg((0, 0), (1, 1)), seg((1.00001, 1.00001), (2, 2))]
    assert not same_copper_support(source, [seg((0, 0), (2, 2))])


def test_width_rounding_is_not_geometry_preservation():
    source = [seg((0, 0), (1, 0), .123456), seg((1, 0), (2, 0), .123456)]
    assert not same_copper_support(source, [seg((0, 0), (2, 0), .1235)])


def test_removing_a_one_nanometre_kink_is_not_geometry_preservation():
    source = [seg((0, 0), (1, 1.000001)), seg((1, 1.000001), (2, 2))]
    assert not same_copper_support(source, [seg((0, 0), (2, 2))])


@pytest.mark.parametrize('reason', ['copper_changed', 'connectivity_changed'])
def test_rejected_merge_never_mutates_live_copper_or_result_custody(monkeypatch, reason):
    from dgloss import krt_merge
    source = [seg((0, 0), (1, 0)), seg((1, 0), (2, 0))]
    replacement = seg((0, 0), (2, 0), .3 if reason == 'copper_changed' else .2)
    pcb = SimpleNamespace(segments=list(source), vias=[])
    apply = Mock()
    context = SimpleNamespace(pcb_data=pcb, branch_scoped=False, apply_replacement=apply)
    results = [{'new_segments': list(source), 'new_vias': []}]
    monkeypatch.setattr(krt_merge, 'ReplacementGuard', lambda *args: lambda *args: False)

    def propose(scratch, trial, scope, **kwargs):
        assert trial is not pcb and trial.segments is not pcb.segments
        trial.segments = [replacement]
        scratch[0]['new_segments'] = [replacement]
        return 1, 1, [], [replacement], {}

    changed, nets, strips, added, stats = krt_merge.merge_in_scope(results, context, [1], propose)
    assert (changed, nets, strips, added) == (0, 0, [], [])
    assert stats['rejections'] == [{'net_id': 1, 'reason': reason}]
    assert pcb.segments == source
    assert results == [{'new_segments': source, 'new_vias': []}]
    apply.assert_not_called()
