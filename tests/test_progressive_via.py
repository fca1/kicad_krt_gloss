import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss.tests.test_g0_g1_g3 import _pad, PCBData, BoardInfo, Net, Segment, Via, GridRouteConfig
from dgloss.context import build_gloss_context
from dgloss.pipeline import _grade, _certify_g5_copper, run_final_gloss
from dgloss.reduction_motion import MotionCertificate
from dgloss import GlossConfig
from tools.progressive_via import move_mobile_vias, progressive_via


def example(points=((8.,5.), (6.,5.), (4.,5.), (2.,5.)), pad_stop=False, junction=False, transform=lambda x,y:(x,y)):
    def p(point): return transform(*point)
    def seg(a,b,layer): return Segment(*p(a),*p(b),.2,layer,1)
    segments = [seg((2.,5.),(8.,5.),'F.Cu')]
    segments += [seg(a,b,'B.Cu') for a,b in zip(points,points[1:])]
    if junction: segments.append(seg((6.,5.),(6.,7.),'B.Cu'))
    pads={1:[_pad('A',*p((2.,5.)),1,size=.1),_pad('B',*p(points[-1]),1,'B.Cu',size=.1)]}
    if pad_stop: pads[1].append(_pad('STOP',*p((6.,5.)),1,'B.Cu',size=.1))
    pcb=PCBData(BoardInfo({},['F.Cu','B.Cu'],(-20.,-20.,20.,20.)),
                {1:Net(1,'N1')},{},[Via(*p((8.,5.)),.5,.2,['F.Cu','B.Cu'],1)],segments,pads)
    cfg=GridRouteConfig(track_width=.2,clearance=.1,grid_step=.1,layers=['F.Cu','B.Cu'],board_edge_clearance=0.)
    return pcb,cfg


@pytest.mark.parametrize('transform',[lambda x,y:(x,y),lambda x,y:(-y,x),lambda x,y:(x-y,x+y)])
def test_absorbs_successive_segments_then_stops_at_pad(transform):
    pcb,cfg=example(transform=transform)
    ctx=build_gloss_context(pcb,cfg,[1]); ctx._reduction_motion=MotionCertificate()
    grade=_grade(pcb,1); initial_via=pcb.vias[0]
    removed, emitted, changes, stats=move_mobile_vias(ctx,[],net_ids=[1])
    assert stats['vias_moved']==3
    assert not pcb.segments
    assert (pcb.vias[0].x,pcb.vias[0].y)==transform(2.,5.)
    assert removed==[initial_via] and emitted==pcb.vias
    assert not stats['added_segments']
    _certify_g5_copper(ctx,{1:grade},changes)


@pytest.mark.parametrize('pad_stop,junction',[(True,False),(False,True)])
def test_stops_at_pad_or_multiple_junction(pad_stop,junction):
    pcb,cfg=example(pad_stop=pad_stop,junction=junction)
    ctx=build_gloss_context(pcb,cfg,[1]); grade=_grade(pcb,1)
    _,_,changes,stats=move_mobile_vias(ctx,[],net_ids=[1])
    assert stats['vias_moved']==1
    assert (pcb.vias[0].x,pcb.vias[0].y)==(6.,5.)
    _certify_g5_copper(ctx,{1:grade},changes)


@pytest.mark.parametrize('corridor',[False,True])
def test_full_pipeline_accepts_both_segments_null(corridor):
    pcb,cfg=example(points=((8.,5.),(2.,5.)))
    with progressive_via():
        result=run_final_gloss([],pcb,cfg,GlossConfig(stay_in_corridor=corridor,repeat_until_stable=False,budget_seconds=2.),net_ids=[1])
    assert result.stats['g5_valid']
    assert result.stats['saved_mm']==pytest.approx(12.)
    assert not pcb.segments


def test_no_gain_when_via_between_anchors():
    pcb,cfg=example(points=((8.,5.),(10.,5.)))
    ctx=build_gloss_context(pcb,cfg,[1])
    assert move_mobile_vias(ctx,[],net_ids=[1])[3]['vias_moved']==0


def test_obstacle_blocks_corridor_even_with_clear_destination():
    pcb,cfg=example(points=((8.,5.),(2.,5.)))
    pcb.nets[2]=Net(2,'BLOCK')
    pcb.pads_by_net[2]=[_pad('X',5.,5.32,2,size=.1)]
    ctx=build_gloss_context(pcb,cfg,[1]); ctx._reduction_motion=MotionCertificate()
    assert move_mobile_vias(ctx,[],net_ids=[1])[3]['vias_moved']==0


def test_progression_on_internal_layer_of_through_via():
    pcb,cfg=example()
    pcb.board_info.copper_layers=['F.Cu','In1.Cu','In2.Cu','B.Cu']
    cfg.layers=list(pcb.board_info.copper_layers)
    for segment in pcb.segments:
        if segment.layer=='B.Cu': segment.layer='In2.Cu'
    pcb.pads_by_net[1][-1].layers=['In2.Cu']
    ctx=build_gloss_context(pcb,cfg,[1]); grade=_grade(pcb,1)
    _,_,changes,stats=move_mobile_vias(ctx,[],net_ids=[1])
    assert stats['vias_moved']==3
    assert not pcb.segments
    _certify_g5_copper(ctx,{1:grade},changes)
