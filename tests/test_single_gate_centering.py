"""Isolated gates must reach construction through the public Centering pipeline."""
import math
import pytest
from test_interpad import _pad
from kicad_parser import BoardInfo, Net, PCBData, Segment
from routing_config import GridRouteConfig
from dgloss.pipeline import run_centering
from dgloss.interpad import find_interpad_doors, _branch_door_groups


@pytest.mark.parametrize('angle', [0, 45, 90, 180])
def test_single_gate_public_pipeline(angle):
    def rotate(p):
        c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
        return c*p[0]-s*p[1],s*p[0]+c*p[1]
    points=list(map(rotate,[(0,1),(.425001,.574999),(7.674999,.574999),(8.05,.95),(11.965,.95)]))
    segments=[Segment(*a,*b,.15,'F.Cu',1) for a,b in zip(points,points[1:])]
    pads={1:[_pad('START',*points[0],1,size=.5),_pad('END',*points[-1],1,size=.5)],
          2:[_pad('AB21',*rotate((.999,0)),2,size=.5)],
          3:[_pad('AB20',*rotate((.999,1)),3,size=.5)]}
    pcb=PCBData(BoardInfo({},['F.Cu'],(-30,-30,30,30)),
                {i:Net(i,str(i)) for i in pads},{},[],segments,pads)
    config=GridRouteConfig(track_width=.15,clearance=.1,grid_step=.1,
                           layers=['F.Cu'],board_edge_clearance=0.)
    scan=find_interpad_doors(pcb,config,net_id=1,proximity_mm=1.)
    assert len(scan.doors)==1
    assert _branch_door_groups(pcb,scan.doors)==[scan.doors]
    outcome=run_centering([],pcb,config,net_ids=[1],proximity_mm=1.,_emit_log=False)
    assert outcome.stats['centering_candidates_considered']>=1
    assert outcome.stats.get('g5_valid') is True
    assert outcome.stats['doors_centered']+outcome.stats.get('doors_already_centered',0)==1
    final=find_interpad_doors(pcb,config,net_id=1,proximity_mm=1.)
    assert len(final.doors)==1
    assert abs(final.doors[0].offset)<1e-7
