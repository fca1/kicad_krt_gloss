"""Diagnostic wrapper for the integrated auto gloss scheduler.

Diagnostic override of the integrated scheduler; no G4 change. The queue operates on complete
anchored chains, not yet individual two/three-segment windows. All candidates,
acceptance rules and KRT validations remain those of the production algorithm.
The patch is process-global: use only in the single-threaded diagnostic runner.
"""
from collections import Counter, deque
from contextlib import contextmanager
from unittest.mock import patch

from dgloss import algorithm, pipeline


from dgloss.auto_gloss import _key, _ends, _signature, revisit_chains


@contextmanager
def auto_gloss(scheduler=revisit_chains):
    """Override/count scheduling for diagnostics, restoring it on every exit."""
    stats = Counter()
    original = algorithm._simple_chains
    original_shorten = pipeline.shorten_routes

    def scheduled(pcb, net, allowed_segment_ids=None):
        return scheduler(original, pcb, net, allowed_segment_ids, stats)

    def shorten(context, results, *args, **kwargs):
        before_ids = {id(s) for s in context.pcb_data.segments}
        strips, added, changes, totals = original_shorten(context, results, *args, **kwargs)
        final_ids = {id(s) for s in context.pcb_data.segments}
        # Intermediate segments were created and consumed inside this stage;
        # they must never become output copper or native deletion requests.
        strips = [s for s in strips if id(s) in before_ids]
        added = [s for s in added if id(s) in final_ids]
        changes.segments = [item for item in changes.segments
                            if ('old' in item and id(item['old']) in before_ids)
                            or ('new' in item and id(item['new']) in final_ids)]
        return strips, added, changes, totals

    with patch.object(algorithm, '_scheduled_chains', scheduled), \
            patch.object(pipeline, 'shorten_routes', shorten):
        yield stats
