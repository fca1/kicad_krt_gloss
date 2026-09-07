"""Auto gloss experiment: full initial search, at most three segments per revisit.

Topology is still rebuilt after edits, to isolate search granularity first.
No joint-objective prototype, no G4. Complete diagnostic calls audit omissions.
"""
from collections import deque
from contextlib import contextmanager
from unittest.mock import patch
from time import perf_counter

from dgloss import algorithm
from dgloss.via_mobile import _creates_boundary_right_angle
from tools.auto_gloss import auto_gloss, _key, _ends, _signature


def affected_windows(chain, touched, added_ids):
    """Consecutive triples covering edited copper/joints; pairs on short chains.

    No Cartesian search or spatial sampling. Preserve chain traversal order and
    its original anchor splits (pads, vias, junctions, width/layer changes).
    """
    size = min(3, len(chain.segments))
    if size < 2:
        return
    for i in range(len(chain.segments) - size + 1):
        segments = chain.segments[i:i + size]
        if not ({id(s) for s in segments} & added_ids or _ends(segments) & touched):
            continue
        window = algorithm._Chain(segments, chain.points[i:i + size + 1],
                                  chain.layer, chain.width)
        window.small_window = True
        yield window


def revisit_windows(original, pcb, net, allowed, stats):
    pending = deque(original(pcb, net, allowed))
    queued = {_key(c) for c in pending}
    visited = set()
    while pending:
        chain = pending.popleft()
        key = _key(chain)
        queued.discard(key)
        current = {id(s) for s in pcb.segments if s.net_id == net}
        if not key <= current:
            stats['stale_windows'] += 1
            continue
        signature = _signature(chain)
        if signature in visited:
            stats['repeated_geometry_skipped'] += 1
            continue
        visited.add(signature)
        small = getattr(chain, 'small_window', False)
        stats['windows_presented' if small else 'initial_chains_presented'] += 1
        if small:
            stats['revisited_segments'] += len(chain.segments)
        yield chain
        after = {id(s): s for s in pcb.segments if s.net_id == net}
        removed = [s for s in chain.segments if id(s) not in after]
        added = [s for ident, s in after.items() if ident not in current]
        if not removed and not added:
            continue
        stats['accepted_window_edits' if small else 'accepted_initial_edits'] += 1
        touched, added_ids = _ends(removed + added), {id(s) for s in added}
        tick = perf_counter()
        chains = original(pcb, net, allowed)
        stats['topology_seconds'] += perf_counter() - tick
        stats['topology_rebuilds'] += 1
        for candidate in chains:
            for window in affected_windows(candidate, touched, added_ids):
                window_key = _key(window)
                if window_key not in queued:
                    pending.append(window)
                    queued.add(window_key)
                    stats['windows_queued'] += 1


@contextmanager
def window_auto_gloss():
    original_best = algorithm._best_chain_replacement

    def bounded(context, chain, net_id, foreign, current, vias, **kwargs):
        if getattr(chain, 'small_window', False):
            guard = kwargs.get('accept_replacement')
            window_ids = _key(chain)
            outside = [s for s in current if id(s) not in window_ids]
            anchors = (chain.points[0], chain.points[-1])
            def accept(removed, added):
                # Artificial window edges must retain the angular rule that
                # the full-chain DAG enforces between its consecutive edges.
                for segment in added:
                    endpoints = ((segment.start_x, segment.start_y),
                                 (segment.end_x, segment.end_y))
                    for anchor in anchors:
                        if anchor in endpoints and _creates_boundary_right_angle(
                                segment, anchor, outside):
                            return False
                return guard(removed, added) if guard else True
            kwargs['accept_replacement'] = accept
        return original_best(context, chain, net_id, foreign, current, vias, **kwargs)

    with patch.object(algorithm, '_best_chain_replacement', bounded), \
            auto_gloss(scheduler=revisit_windows) as stats:
        yield stats
