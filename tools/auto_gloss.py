"""Opt-in auto gloss prototype: revisit modified chains inside each G3 stage.

No G4 and no change to production entry points. The queue operates on complete
anchored chains, not yet individual two/three-segment windows. All candidates,
acceptance rules and KRT validations remain those of the production algorithm.
The patch is process-global: use only in the single-threaded diagnostic runner.
"""
from collections import Counter, deque
from contextlib import contextmanager
from unittest.mock import patch

from dgloss import algorithm, pipeline


def _key(chain):
    return frozenset(id(s) for s in chain.segments)


def _ends(segments):
    return {(s.layer, x, y) for s in segments
            for x, y in ((s.start_x, s.start_y), (s.end_x, s.end_y))}


def _signature(chain):
    return tuple(sorted((s.layer, s.width,
                         *sorted(((s.start_x, s.start_y), (s.end_x, s.end_y))))
                        for s in chain.segments))


def revisit_chains(original, pcb, net, allowed, stats):
    """Resume after each accepted edit and queue only incident changed chains.

    The consumer owns mutation, deadline checking and validation. Rebuilding
    topology is necessary after an edit, but does not run candidate searches on
    unaffected chains. Repeated geometry is suppressed and counted; this is a
    safety stop, not a certificate of whole-net convergence.
    """
    pending = deque(original(pcb, net, allowed))
    queued = {_key(c) for c in pending}
    visited = set()
    while pending:
        chain = pending.popleft()
        key = _key(chain)
        queued.discard(key)
        current = {id(s) for s in pcb.segments if s.net_id == net}
        if not key <= current:
            stats['stale_chains'] += 1
            continue
        signature = _signature(chain)
        if signature in visited:
            stats['repeated_geometry_skipped'] += 1
            continue
        visited.add(signature)
        stats['chains_searched'] += 1
        yield chain
        after = {id(s): s for s in pcb.segments if s.net_id == net}
        removed = [s for s in chain.segments if id(s) not in after]
        added = [s for ident, s in after.items() if ident not in current]
        if not removed and not added:
            continue
        stats['accepted_chain_edits'] += 1
        touched = _ends(removed + added)
        added_ids = {id(s) for s in added}
        stats['topology_rebuilds'] += 1
        for candidate in original(pcb, net, allowed):
            candidate_key = _key(candidate)
            if candidate_key in queued:
                continue
            if (candidate_key & added_ids or
                    _ends(candidate.segments) & touched):
                pending.append(candidate)
                queued.add(candidate_key)
                stats['chains_requeued'] += 1


@contextmanager
def auto_gloss(scheduler=revisit_chains):
    """Enable the experimental scheduler, restoring production on every exit."""
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

    with patch.object(algorithm, '_simple_chains', scheduled), \
            patch.object(pipeline, 'shorten_routes', shorten):
        yield stats
