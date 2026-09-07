from dataclasses import replace
from unittest.mock import Mock
from test_adaptive_segment_slide import fixture
from dgloss.krt_api import Segment
from tools.adaptive_segment_slide import best_slide,SearchStats
from tools.slide_failure_cache import WindowCache


def test_per_candidate_limit_allows_smaller_certified_trial(monkeypatch):
    ctx,source,points=fixture()
    # An inconclusive large envelope; narrower envelopes certify normally.
    monkeypatch.setattr(ctx.clearance_adapter,'segment_clears',lambda s:s.width<=.25)
    stats=SearchStats()
    result=best_slide(ctx,source,[],[],(points[0],points[-1]),stats=stats,
                      max_candidate_probes=12,max_candidates=3)
    assert stats.candidate_capped>=1
    assert stats.candidates==3
    assert stats.segment_probes<=36
    assert result is not None
    assert result[1].start_y>2


def test_candidate_limit_does_not_accept_thin_obstacle_crossing():
    ctx,source,points=fixture(width=.01,obstacle_y=2.05,clearance=.005)
    result=best_slide(ctx,source,[],[],(points[0],points[-1]),
                      stats=SearchStats(),max_candidate_probes=32)
    assert result is None or result[1].start_y<2.05


def test_cache_reuses_equivalent_geometry_and_invalidates_local_outside():
    ctx,source,points=fixture();cache=WindowCache();stats=SearchStats()
    original=Mock(return_value=None)
    anchors=(points[0],points[-1])
    cache.search(original,ctx,source,[],[],anchors,stats=stats)
    cache.search(original,ctx,[replace(s) for s in source],[],[],anchors,stats=stats)
    assert original.call_count==1 and cache.stats['hits']==1
    outside=[Segment(0,8,1,8,.2,'F.Cu',1)]
    cache.search(original,ctx,source,outside,[],anchors,stats=stats)
    assert original.call_count==2


def test_cache_invalidates_nearby_foreign_and_committed_own_copper():
    ctx,source,points=fixture();cache=WindowCache();stats=SearchStats()
    original=Mock(return_value=None);anchors=(points[0],points[-1])
    cache.search(original,ctx,source,[],[],anchors,stats=stats)
    for net in (2,1):
        ctx.search_cache.changed([Segment(4,3,5,3,.2,'F.Cu',net)])
        cache.search(original,ctx,source,[],[],anchors,stats=stats)
    assert original.call_count==3 and cache.stats['invalidations']==2


def test_cache_does_not_store_exhausted_search_or_mix_policies():
    ctx,source,points=fixture();cache=WindowCache();stats=SearchStats()
    def capped(*args,**kwargs):stats.capped+=1
    original=Mock(side_effect=capped);anchors=(points[0],points[-1])
    for _ in range(2):cache.search(original,ctx,source,[],[],anchors,stats=stats)
    assert original.call_count==2 and cache.stats['stored']==0
    original.side_effect=None
    cache.search(original,ctx,source,[],[],anchors,stats=stats,stay_in_corridor=True)
    cache.search(original,ctx,source,[],[],anchors,stats=stats,stay_in_corridor=False)
    assert original.call_count==4
