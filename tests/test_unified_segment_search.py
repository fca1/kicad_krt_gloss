from unittest.mock import Mock
import pytest
from test_adaptive_segment_slide import fixture
from dgloss import algorithm
from dgloss.algorithm import _Chain
from dgloss.krt_api import calculate_route_length
from tools.adaptive_segment_slide import SearchStats, best_slide
from tools.adaptive_slide_local import local_replacement
from tools.unified_segment_search import activate


@pytest.mark.parametrize('corridor',[False,True])
def test_both_modes_dispatch_to_common_local_search(monkeypatch,corridor):
    ctx,source,points=fixture()
    forbidden=Mock(side_effect=AssertionError('broad chain search must not run'))
    monkeypatch.setattr(algorithm,'_best_chain_replacement',forbidden)
    with activate(SearchStats()):
        _,added,_,stats=algorithm.shorten_routes(ctx,[],net_ids=[1],stay_in_corridor=corridor)
    assert added
    assert stats['saved_mm']>0
    forbidden.assert_not_called()


def test_disabling_corridor_keeps_exact_and_connectivity_checks(monkeypatch):
    ctx,source,points=fixture()
    exact=Mock(return_value=False)
    monkeypatch.setattr(ctx.clearance_adapter,'segment_clears',exact)
    assert best_slide(ctx,source,[],[],(points[0],points[-1]),stay_in_corridor=False) is None
    assert exact.called
    monkeypatch.setattr(ctx.clearance_adapter,'segment_clears',lambda s:True)
    guard=Mock(return_value=False)
    assert best_slide(ctx,source,[],[],(points[0],points[-1]),
                      stay_in_corridor=False,accept_replacement=guard) is None
    assert guard.called


def test_unconstrained_mode_can_take_shortcut_blocked_only_by_sweep():
    gains=[]
    for corridor in (True,False):
        ctx,source,points=fixture()
        result=local_replacement(ctx,_Chain(source,points,'F.Cu',.2),1,source,[],
                                 stay_in_corridor=corridor,stats=SearchStats())
        assert result is not None
        removed,added=result
        assert ctx.clearance_adapter.connector_clears(added)
        gains.append(calculate_route_length(removed)-calculate_route_length(added))
    assert gains[1]>gains[0]>0


def test_redundant_late_local_pass_is_empty():
    ctx,source,_=fixture()
    with activate(SearchStats()):
        removed,added,changes,stats=algorithm.shorten_routes(
            ctx,[],net_ids=[1],local_only=True,stage='G3 local')
    assert not removed and not added and not changes.segments
    assert stats['saved_mm']==0
    assert all(a is b for a,b in zip(ctx.pcb_data.segments,source))
