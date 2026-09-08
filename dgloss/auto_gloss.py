"""Revisit only changed or incident complete chains within a reduction stage."""
from collections import deque
from .board_views import board_views


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
        current = {id(s) for s in board_views(pcb).segments(net)}
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
        after = {id(s): s for s in board_views(pcb).segments(net)}
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


