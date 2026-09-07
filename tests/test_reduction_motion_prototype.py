"""Synthetic checks of the integrated joint-motion certificate; real KRT clearance predicates."""
from contextlib import nullcontext
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest

from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from kicad_parser import Segment, Via, PCBData, BoardInfo, Net
from routing_config import GridRouteConfig
from dgloss.tests.test_g0_g1_g3 import _pad
from dgloss.context import build_gloss_context
from dgloss.sliding_nodes import slide_t_nodes
from dgloss.reduction_motion import MotionCertificate
from dgloss.pad_terminals import _best_pad_connector as streaming_pad


def test_pipeline_enables_reuses_and_disables_motion_with_corridor_policy():
    from dgloss import GlossConfig
    from dgloss.pipeline import _run_optimization_pass
    from dgloss.execution import perf_counter
    ctx = board([], [], {1: []})
    def run(required):
        _run_optimization_pass([], ctx, GlossConfig(stay_in_corridor=required),
                               [], perf_counter() + 1., emit_log=False)
    run(True)
    certificate = ctx._reduction_motion
    assert isinstance(certificate, MotionCertificate)
    run(True)
    assert ctx._reduction_motion is certificate
    run(False)
    assert ctx._reduction_motion is None


def board(segments, vias, pads, width=.2, clearance=.1):
    pcb = PCBData(BoardInfo({}, ['F.Cu','B.Cu'], (-2,-2,10,8)),
                  {1:Net(1,'N1'), 2:Net(2,'OBSTACLE')}, {}, vias, segments, pads)
    cfg = GridRouteConfig(track_width=width, clearance=clearance, grid_step=.1,
                          layers=['F.Cu','B.Cu'], board_edge_clearance=0.)
    return build_gloss_context(pcb, cfg, net_ids=[1])


@pytest.mark.parametrize('blocked', [False, True])
def test_t_motion_is_accepted_only_without_the_swept_obstacle(blocked):
    source = [Segment(1,2,3,2,.2,'F.Cu',1),Segment(3,2,7,2,.2,'F.Cu',1),
              Segment(3,2,4,1,.2,'F.Cu',1),Segment(4,1,6,1,.2,'F.Cu',1)]
    pads = {1:[_pad('L',1,2,1),_pad('R',7,2,1),_pad('B',6,1,1)],
            2:[_pad('X',5,1.5,2,size=.2)] if blocked else []}
    ctx = board(source, [], pads)
    candidate = [Segment(6,1,6,2,.2,'F.Cu',1)]
    assert ctx.clearance_adapter.connector_clears(source + candidate)
    motion = MotionCertificate()
    assert motion.junction(ctx, source[2:], candidate, (3,2), (6,1), None) is not blocked
    ctx._reduction_motion = motion
    _, added, _, stats = slide_t_nodes(ctx, [], net_ids=[1])
    assert stats['t_branches_slid'] == (0 if blocked else 1)


def test_via_body_is_checked_together_with_its_incident_tracks():
    source = [Segment(1,1,3,1,.05,'F.Cu',1), Segment(3,1,3,4,.05,'B.Cu',1)]
    old = Via(3,1,.6,.2,['F.Cu','B.Cu'],1)
    new = Via(1,2,.6,.2,['F.Cu','B.Cu'],1)
    pads = {1:[_pad('A',1,1,1),_pad('B',3,4,1,'B.Cu')],
            2:[_pad('X',2,1.7,2,size=.1)]}
    ctx = board(source, [old], pads, width=.05, clearance=.05)
    paths = [([(1,1),(3,1)], [(1,1),(1,2)], source[0]),
             ([(3,4),(3,1)], [(3,4),(1,2)], source[1])]
    motion = MotionCertificate()
    assert ctx.clearance_adapter.via_clears(old, ignored_via=old)
    assert ctx.clearance_adapter.via_clears(new, ignored_via=old)
    assert motion.certify(ctx, paths)
    assert not motion.certify(ctx, paths, old, new)


def test_expired_certificate_never_accepts_unchecked_motion():
    source = Segment(0,0,2,0,.2,'F.Cu',1)
    ctx = board([source], [], {1:[]})
    assert not MotionCertificate().certify(ctx, [([(0,0),(2,0)],[(0,0),(2,1)],source)], deadline=0)


def test_streaming_pad_retains_certified_candidate_when_next_family_expires(monkeypatch):
    from dgloss import pad_terminals as p
    from dgloss.algorithm import _ClearanceDecision
    import dgloss.pad_terminals as module
    now = [0.]
    candidate = [Segment(0,0,5,5,.2,'F.Cu',1)]
    source = [Segment(0,0,0,5,.2,'F.Cu',1),Segment(0,5,5,5,.2,'F.Cu',1)]
    def families(*args):
        yield 'canonical', [candidate]
        now[0] = 2.
        yield 'chamfer', [candidate]
    monkeypatch.setattr(module, 'perf_counter', lambda: now[0])
    monkeypatch.setattr(p, '_connector_families', families)
    monkeypatch.setattr(p, '_candidate_clearance', lambda *a, **k: _ClearanceDecision(True))
    exact = Mock(return_value=True)
    ctx = NS(coord=NS(grid_step=.1),clearance_adapter=NS(
        connector_clears=exact,stable_copper=nullcontext))
    result = streaming_pad(ctx, NS(global_x=0,global_y=0),source,
                           [(0,0),(0,5),(5,5)],[],[],None,deadline=1.)
    assert result is candidate
    assert exact.call_count == 1
