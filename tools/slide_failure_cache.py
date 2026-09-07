"""Independent failed-window cache experiment using Gloss invalidation rules.

Canonical source identities permit reuse after equivalent reconstruction.
The complete outside same-net geometry is in the key because local edits are
not yet published through context.replace_editable_segments. Foreign copper
and committed same-net changes use the existing SearchCache invalidations.
"""
from collections import OrderedDict
from contextlib import contextmanager
from unittest.mock import patch

from dgloss.execution import perf_counter
import tools.adaptive_segment_slide as adaptive


def segment_key(s):
    ends=sorted(((s.start_x,s.start_y),(s.end_x,s.end_y)))
    return (*ends,s.width,s.layer,s.net_id,getattr(s,'locked',False))


def via_key(v):
    return (v.x,v.y,v.size,v.drill,tuple(v.layers),v.net_id,getattr(v,'locked',False))


class WindowCache:
    def __init__(self):
        self.stats=dict(hits=0,misses=0,stored=0,invalidations=0,seconds=0.)
        self.sources=OrderedDict()

    def search(self,original,context,source,outside,vias,anchors,deadline=None,**kwargs):
        started=perf_counter()
        cache=getattr(context,'search_cache',None)
        stats=kwargs.get('stats')
        if cache is None or stats is None:
            return original(context,source,outside,vias,anchors,deadline,**kwargs)
        if deadline is not None and perf_counter() >= deadline:
            return None
        signature=(id(context),tuple(segment_key(s) for s in source))
        canonical=self.sources.get(signature)
        if canonical is None:
            canonical=tuple(source)
            self.sources[signature]=canonical
            if len(self.sources)>512:
                self.sources.popitem(last=False)
        self.sources.move_to_end(signature)
        policy=(tuple(sorted(segment_key(s) for s in outside)),
                tuple(sorted(via_key(v) for v in vias)),tuple(anchors),
                kwargs.get('stay_in_corridor',True),kwargs.get('max_candidates',32),
                kwargs.get('max_probes',512),kwargs.get('max_candidate_probes'),
                kwargs.get('accept_replacement') is not None)
        invalidations=cache.stats['invalidations']
        token,hit=cache.token('adaptive_window',source[0].net_id,canonical,policy)
        self.stats['invalidations']+=cache.stats['invalidations']-invalidations
        self.stats['seconds']+=perf_counter()-started
        if hit:
            self.stats['hits']+=1
            return None
        self.stats['misses']+=1
        capped,local_capped,neutral=stats.capped,stats.candidate_capped,stats.neutral
        probes,candidates=stats.segment_probes,stats.candidates
        result=original(context,source,outside,vias,anchors,deadline,**kwargs)
        if (result is None and stats.capped==capped and stats.candidate_capped==local_capped
                and stats.segment_probes-probes < kwargs.get('max_probes',512)
                and stats.candidates-candidates < kwargs.get('max_candidates',32)
                and stats.neutral==neutral and (deadline is None or perf_counter()<deadline)):
            started=perf_counter()
            cache.remember_failure(token,canonical)
            self.stats['stored']+=1
            self.stats['seconds']+=perf_counter()-started
        return result


@contextmanager
def activate(cache):
    original=adaptive.best_slide
    def wrapped(*args,**kwargs):
        return cache.search(original,*args,**kwargs)
    with patch.object(adaptive,'best_slide',wrapped):
        yield
