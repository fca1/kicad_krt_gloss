"""Experimental common local reduction; only validation depends on corridor.

Use the existing adaptive candidate search unchanged. Do not mix this trial
with new budgets, Rust filters, caches, or alternative envelope algorithms.
"""
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def activate(stats):
    from dgloss import algorithm, local_gloss, pipeline
    from tools.adaptive_slide_local import local_replacement
    original=algorithm.shorten_routes
    policy=[True]
    def local(*args,**kwargs):
        return local_replacement(*args,stats=stats,stay_in_corridor=policy[-1],**kwargs)
    def shorten(context,results,deadline=None,**kwargs):
        if kwargs.get('stage')=='G3 local':
            # G3 already used the common local engine; avoid a second pass that
            # would otherwise exist only when corridor is disabled.
            return original(context,results,deadline,**dict(kwargs,net_ids=[]))
        if kwargs.get('objective','shorter')=='shorter':
            kwargs['local_only']=True
        policy.append(kwargs.get('stay_in_corridor',False))
        try:return original(context,results,deadline,**kwargs)
        finally:policy.pop()
    with (patch.object(local_gloss,'local_replacement',local),
          patch.object(pipeline,'shorten_routes',shorten),
          patch.object(algorithm,'shorten_routes',shorten)):
        yield
