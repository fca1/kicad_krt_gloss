from types import SimpleNamespace
import pytest
import gloss
from dgloss.changes import GlossChanges
from dgloss.krt_api import Segment
from tools.dependency_g4 import Dependencies, marginal_stop, run_worklist


def tracker(max_cells=4096):
    return Dependencies(SimpleNamespace(zones=[]),
        SimpleNamespace(layers=['F.Cu','B.Cu'],clearance=.2),max_cells=max_cells)


def seg(net, x=0, layer='F.Cu'):
    return Segment(x,0,x+1,0,.2,layer,net)


def test_changed_foreign_copper_wakes_failed_search_but_distant_copper_does_not():
    deps=tracker();deps.watch(seg(1))
    assert deps.affected(GlossChanges(segments=[{'old':seg(2)}]),{1,2})=={1,2}
    assert deps.affected(GlossChanges(segments=[{'old':seg(2,100)}]),{1,2})=={2}
    assert deps.affected(GlossChanges(segments=[{'new':seg(2,0,'B.Cu')}]),{1,2})=={2}


def test_large_uncertain_region_and_zone_dependencies_wake_conservatively():
    deps=tracker(max_cells=1)
    deps.watch(Segment(0,0,100,100,.2,'F.Cu',1))
    deps.zone_nets.add(3)
    assert deps.affected(GlossChanges(segments=[{'old':seg(2,500)}]),{1,2,3})=={1,2,3}


@pytest.mark.parametrize('pass_no,gain,previous,expected',[
    (2,.001,1,False),(3,.01,1,True),(3,.0101,1,False),
    (4,0,1,True),(3,0,0,False),(3,1,0,False)])
def test_incremental_gain_threshold(pass_no,gain,previous,expected):
    assert marginal_stop(pass_no,gain,previous)==expected


def test_quiet_targeted_wave_requires_full_audit():
    deps=tracker()
    initial={'changes':GlossChanges(segments=[{'old':seg(1)}]),
             'changed_net_ids':{1},'before_length':10.,'after_length':9.}
    controller=SimpleNamespace(dependencies=deps,initial=initial,percent=1.)
    context=SimpleNamespace(pcb_data=SimpleNamespace(segments=[]),net_ids=[1,2])
    orders=[]
    def run(*args,**kwargs):
        orders.append(list(args[3]))
        return dict(changes=GlossChanges(),segment_strips=[],via_strips=[],
            g3={},via={},pad={},node={},refine={},merge={},
            equal={'segments_removed':0,'segments_added':0},merged_count=0,
            merged_nets=0,merge_ms=0,changed_net_ids=set(),
            stage_stats=SimpleNamespace(as_dict=lambda:{'stages':{}}))
    result=run_worklist(context,None,[1,2],[],float('inf'),run,controller=controller)
    assert orders==[[1],[2,1]]
    assert result['stop_reason']=='converged'


def test_third_total_pass_stops_on_marginal_gain_and_keeps_the_result():
    deps=tracker()
    original=Segment(0,0,10,0,.2,'F.Cu',1)
    controller=SimpleNamespace(dependencies=deps,percent=1.,initial={
        'changes':GlossChanges(segments=[{'new':original}]),
        'changed_net_ids':{1},'before_length':12.,'after_length':10.})
    context=SimpleNamespace(pcb_data=SimpleNamespace(segments=[original]),net_ids=[1])
    lengths=iter([9.,8.995])
    def run(*args,**kwargs):
        old=context.pcb_data.segments[0]
        new=Segment(0,0,next(lengths),0,.2,'F.Cu',1)
        context.pcb_data.segments=[new]
        return dict(changes=GlossChanges(segments=[{'old':old},{'new':new}]),
            segment_strips=[],via_strips=[],g3={},via={},pad={},node={},refine={},merge={},
            equal={'segments_removed':0,'segments_added':0},merged_count=0,
            merged_nets=0,merge_ms=0,changed_net_ids={1},
            stage_stats=SimpleNamespace(as_dict=lambda:{'stages':{'G3':{'changes':1}}}))
    result=run_worklist(context,None,[1],[],float('inf'),run,controller=controller)
    assert result['stop_reason']=='marginal_gain'
    assert [p['total_pass'] for p in result['passes']]==[2,3]
    assert result['saved_mm']==pytest.approx(1.005)
    assert context.pcb_data.segments[0].end_x==8.995
