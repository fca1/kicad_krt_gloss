from types import SimpleNamespace as NS
import pytest
from kicad_krt_gloss.branch_selection_prototype import Branch, BranchMemory, StaleBranches, thin_overlay_lines
from kicad_krt_gloss.debug_overlay import overlay_lines
from dgloss.krt_api import Segment


def fixture():
    a=Segment(0,0,2,0,.2,'F.Cu',1)
    b=Segment(2,0,4,0,.2,'F.Cu',1)
    c=Segment(2,0,2,2,.2,'F.Cu',1)
    d=Segment(10,0,12,0,.2,'F.Cu',2)
    pcb=NS(segments=[a,b,c,d],vias=[],pads_by_net={},
           board_info=NS(copper_layers=['F.Cu']),nets={1:NS(name='A'),2:NS(name='B')})
    return pcb,dict(zip('abcd',pcb.segments))


def test_add_replace_clear_and_deduplicate():
    m=BranchMemory()
    m.import_branches({'A':[Branch(frozenset('a'))]},add=True)
    m.import_branches({'A':[Branch(frozenset('a')),Branch(frozenset('b'))]},add=True)
    assert len(m.by_net['A'])==2
    m.import_branches({'B':[Branch(frozenset('d'))]},add=False)
    assert set(m.by_net)=={'B'}
    m.clear()
    assert not m.by_net


def test_branches_or_whole_net_and_toggle_does_not_erase():
    pcb,index=fixture();m=BranchMemory()
    m.import_branches({'A':[Branch(frozenset('a')),Branch(frozenset('c'))]},add=True)
    assert {id(s) for s in m.resolve(pcb,['A'],index)}=={id(index[x]) for x in 'ac'}
    assert len(m.resolve(pcb,['A','B'],index))==3
    assert len(m.resolve(pcb,['A'],index,enabled=False))==3
    assert len(m.resolve(pcb,['A'],index))==2
    assert m.resolve(pcb,[],index)==[]


def test_deleted_branch_never_becomes_whole_net():
    pcb,index=fixture();m=BranchMemory()
    m.import_branches({'A':[Branch(frozenset('a'))]},add=True)
    del index['a']
    with pytest.raises(StaleBranches):m.resolve(pcb,['A'],index)


def test_complete_coverage_promotes_only_complete_net():
    pcb,index=fixture();m=BranchMemory()
    m.import_branches({'A':[Branch(frozenset(x)) for x in 'ac']},add=True)
    assert m.promote_complete_nets(pcb,index,['A'])==set()
    m.import_branches({'A':[Branch(frozenset('b'))]},add=True)
    assert m.promote_complete_nets(pcb,index,['A'])=={'A'}
    assert 'A' not in m.by_net
    assert len(m.resolve(pcb,['A'],index))==3


def test_missing_or_stale_mapping_never_promotes():
    pcb,index=fixture();m=BranchMemory()
    m.import_branches({'A':[Branch(frozenset(x)) for x in 'abc']},add=True)
    del index['c']
    assert not m.promote_complete_nets(pcb,index,['A'])
    assert 'A' in m.by_net


def test_same_count_wrong_track_ids_does_not_promote():
    pcb,index=fixture();m=BranchMemory()
    m.import_branches({'A':[Branch(frozenset(x)) for x in 'abd']},add=True)
    assert not m.promote_complete_nets(pcb,index,['A'])


def test_changed_topology_requires_reimport():
    pcb,index=fixture();m=BranchMemory()
    m.import_branches({'A':[Branch(frozenset('a'))]},add=True)
    pcb.segments.remove(index['c'])
    with pytest.raises(StaleBranches):m.resolve(pcb,['A'],index)


@pytest.mark.parametrize('width',[.05,.1,.2,.8])
def test_only_full_new_overlay_is_thin(width):
    old=Segment(0,0,3,0,width,'F.Cu',1)
    new=Segment(0,1,3,1,width,'F.Cu',1)
    changes={'segments':[{'old':old},{'new':new}]}
    normal=list(overlay_lines(changes));thin=list(thin_overlay_lines(changes))
    assert thin[0]==((0,1),(3,1),.1)
    assert thin[1:]==normal[1:]
    assert old.width==width and new.width==width
