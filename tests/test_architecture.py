"""Regression guards for shared views, electrical references and rollback."""
from types import SimpleNamespace
import pytest

from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss.board_views import board_views
from dgloss.route_geometry import _pad_holds_point
from dgloss.chain_topology import _simple_chains
from dgloss.topology import ReplacementGuard, reference_connectivity
from dgloss.transaction import _restore, _result_snapshot
from dgloss import topology
from dgloss.zone_models import krt
from test_progressive_via import example
from dgloss.tests.test_g0_g1_g3 import _pad, Segment
from dgloss.context import build_gloss_context


@pytest.mark.parametrize('rotation', [0., 30., 90.])
def test_indexed_pad_contacts_match_exact_scan(rotation):
    pcb, _ = example()
    pad = _pad('ROTATED', 0., 0., 1, size=2.)
    pad.rect_rotation = rotation
    pad.size_y = .4
    pcb.pads_by_net[1].append(pad)
    pcb.pads_by_net[2] = [_pad('FOREIGN', 12., 0., 2, size=2.)]
    pcb.segments.append(Segment(0., 0., 1., 0., 5., 'F.Cu', 1))
    views = board_views(pcb)
    for layer in ['F.Cu', 'B.Cu', 'In1.Cu']:
        for width in [.05, .1, 2.5]:
            for x in [-3., -1., -.9, 0., 1., 2., 6., 8., 12.]:
                for y in [-1., -.2, 0., .2, 1., 5.]:
                    point = x, y
                    expected = any(_pad_holds_point(p, point, layer, width)
                                   for p in pcb.pads_by_net[1])
                    assert views.pad_holds(1, point, layer, width) == expected


def test_rollback_discards_zone_models_and_retains_other_snapshot_lookup(monkeypatch):
    pcb, _ = example()
    original = list(pcb.segments)
    owned, external = object(), object()
    setattr(pcb, krt._CACHE_ATTR, {(1, 'F.Cu', 11): owned,
                                 (1, 'F.Cu', 12): object()})
    monkeypatch.setattr(krt, '_MODELS_BY_ZONE_ID', {11: owned, 12: external})
    board_views(pcb)
    pcb._gloss_reference_grades = {1: object()}
    result = {'new_segments': original[:1], 'new_vias': []}
    results = [result]
    snapshot = _result_snapshot(results)
    pcb.segments = []
    result['new_segments'] = []
    _restore(results, 1, snapshot, pcb, original, pcb.vias)
    assert pcb.segments == original
    assert result['new_segments'] == original[:1]
    assert getattr(pcb, krt._CACHE_ATTR) == {}
    assert krt._MODELS_BY_ZONE_ID == {12: external}
    assert pcb._gloss_reference_grades == {}
    assert pcb._gloss_views is None


def test_guards_share_only_reference_graph_and_invalidate_after_commit(monkeypatch):
    pcb, cfg = example()
    context = build_gloss_context(pcb, cfg, [1])
    calls = []
    def check(*args, **kwargs):
        calls.append(args[1])
        return {'connected': True, 'num_components': 1}
    monkeypatch.setattr(topology, 'check_local_connectivity', check)
    old = pcb.segments[0]
    new = Segment(old.start_x, old.start_y, old.end_x - 1., old.end_y,
                  old.width, old.layer, 1)
    for _ in range(2):
        guard = ReplacementGuard(pcb, 1, list(pcb.segments), list(pcb.vias))
        assert guard([old], [new])
    assert len(calls) == 3  # one reference, two distinct trial certificates
    context.apply_replacement([old], [new])
    reference_connectivity(pcb, 1, pcb.segments, pcb.vias)
    assert len(calls) == 4
    assert old not in board_views(pcb).segments(1)
    assert new in board_views(pcb).segments(1)


def test_chain_cache_respects_new_via_anchors_and_editable_scope():
    pcb, cfg = example(points=((8.,5.), (6.,5.), (4.,5.), (2.,5.)))
    context = build_gloss_context(pcb, cfg, [1])
    initial = _simple_chains(pcb, 1)
    assert any(len(chain.segments) == 3 for chain in initial)
    from dataclasses import replace
    moved = replace(pcb.vias[0], x=6.)
    context.apply_replacement([], [], pcb.vias, [moved])
    after = _simple_chains(pcb, 1)
    assert all(len(chain.segments) < 3 for chain in after)
    allowed = {id(pcb.segments[-1])}
    assert _simple_chains(pcb, 1, allowed) == []


@pytest.mark.parametrize('has_zone', [False, True])
def test_foreign_edit_invalidates_zone_references_and_final_grade_stays_uncached(monkeypatch, has_zone):
    pcb, cfg = example()
    context = build_gloss_context(pcb, cfg, [1])
    pcb.zones = [SimpleNamespace(net_id=1, polygon=[])] if has_zone else []
    calls = []
    def check(*args, **kwargs):
        calls.append(args[0])
        return {'connected': True}
    monkeypatch.setattr(topology, '_check', check)
    reference_connectivity(pcb, 1, pcb.segments, pcb.vias)
    reference_connectivity(pcb, 1, pcb.segments, pcb.vias)
    assert calls == [1]
    own = list(pcb.segments)
    foreign = Segment(15., 15., 16., 15., .2, 'F.Cu', 2)
    context.apply_replacement([], [foreign])
    reference_connectivity(pcb, 1, own, pcb.vias)
    assert calls == [1] * (2 if has_zone else 1)
    from dgloss import certification
    monkeypatch.setattr(certification, 'check_net_connectivity', check)
    certification._g5_grade(pcb, 1)
    certification._g5_grade(pcb, 1)
    assert calls == [1] * (4 if has_zone else 3)
