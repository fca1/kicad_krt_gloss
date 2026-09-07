"""Opt-in joint-motion prototype; no UI settings and no KRT modifications.

Certify intervals of a prescribed deformation using inflated KRT probes.
Clear intervals stop immediately; only inconclusive intervals are subdivided.
This is a conservative certificate, not a search for a path around obstacles.
"""
from collections import defaultdict
from dataclasses import replace
from contextlib import contextmanager
import math
from time import perf_counter
from unittest.mock import patch

from kicad_parser import Segment
from dgloss.corridor import _parameterize, _at


def key(p):
    return tuple(round(v, 6) for v in p)


def ends(s):
    return (s.start_x, s.start_y), (s.end_x, s.end_y)


def graph(segments):
    adjacency = defaultdict(list)
    for s in segments:
        for p in ends(s):
            adjacency[key(p)].append(s)
    return adjacency


def path(segments, start, target=None):
    adjacency = graph(segments)
    points, used = [start], set()
    while True:
        current = points[-1]
        if len(points) > 1 and (key(current) == key(target) if target is not None
                               else len(adjacency[key(current)]) != 2):
            return points
        choices = [s for s in adjacency[key(current)] if id(s) not in used]
        if len(choices) != 1:
            return None
        seg = choices[0]
        used.add(id(seg))
        a, b = ends(seg)
        points.append(b if key(a) == key(current) else a)


class MotionCertificate:
    def __init__(self):
        self.stats = dict(via_checks=0, junction_checks=0, rejected=0,
                          intervals=0, segment_probes=0, via_probes=0,
                          capped=0, seconds=0.)

    def certify(self, context, paths, old_via=None, new_via=None, deadline=None):
        started = perf_counter()
        try:
            return self._certify(context, paths, old_via, new_via, deadline)
        finally:
            self.stats['seconds'] += perf_counter() - started

    def _certify(self, context, paths, old_via, new_via, deadline):
        prepared = []
        for source, target, template in paths:
            if source is None or target is None:
                self.stats['rejected'] += 1
                return False
            old_knots = _parameterize(source) or [0., 1.]
            new_knots = _parameterize(target) or [0., 1.]
            knots = sorted(set(old_knots + new_knots))
            old = [_at(source, old_knots, k) for k in knots]
            new = [_at(target, new_knots, k) for k in knots]
            prepared.append((old, new, template))
        stack, count = [(0., 1., 0)], 0
        with context.clearance_adapter.stable_copper():
            while stack:
                if (deadline is not None and perf_counter() >= deadline) or count >= 128:
                    self.stats['capped'] += 1
                    self.stats['rejected'] += 1
                    return False
                low, high, depth = stack.pop()
                count += 1
                self.stats['intervals'] += 1
                mid, half = (low + high) / 2, (high - low) / 2
                clear = True
                for old, new, template in prepared:
                    pts = [(a[0]+mid*(b[0]-a[0]), a[1]+mid*(b[1]-a[1]))
                           for a, b in zip(old, new)]
                    for i, (a, b) in enumerate(zip(pts, pts[1:])):
                        radius = half * max(math.dist(old[i], new[i]),
                                            math.dist(old[i+1], new[i+1]))
                        seg = Segment(*a, *b, template.width + 2*radius,
                                      template.layer, template.net_id)
                        self.stats['segment_probes'] += 1
                        if not context.clearance_adapter.segment_clears(seg):
                            clear = False
                            break
                    if not clear:
                        break
                if clear and old_via is not None:
                    dx, dy = new_via.x-old_via.x, new_via.y-old_via.y
                    radius = half * math.hypot(dx, dy)
                    probe = replace(old_via, x=old_via.x+mid*dx,
                                    y=old_via.y+mid*dy, size=old_via.size+2*radius,
                                    drill=old_via.drill+2*radius)
                    self.stats['via_probes'] += 1
                    clear = context.clearance_adapter.via_clears(probe, ignored_via=old_via)
                if not clear:
                    if depth >= 10:
                        self.stats['rejected'] += 1
                        return False
                    stack.extend([(mid, high, depth+1), (low, mid, depth+1)])
        return True

    def via(self, context, chains, anchors, old_via, new_via, legs, deadline):
        self.stats['via_checks'] += 1
        paths = [(path(chain, anchor, (old_via.x, old_via.y)),
                  [anchor, (new_via.x, new_via.y)], chain[0])
                 for chain, anchor in zip(chains, anchors)]
        return self.certify(context, paths, old_via, new_via, deadline)

    def junction(self, context, removed, added, node, anchor, deadline):
        self.stats['junction_checks'] += 1
        lead = path(added, anchor)
        if lead is None:
            self.stats['rejected'] += 1
            return False
        new_node = lead[-1]
        adjacency = graph(removed)
        fixed = [p for p, edges in adjacency.items() if len(edges) == 1 and p != key(node)]
        paths = [(path(removed, p, node), path(added, p, new_node), adjacency[p][0])
                 for p in fixed]
        return bool(paths) and self.certify(context, paths, deadline=deadline)


@contextmanager
def activate(motion=None, early_pad=False):
    """Attach the prototype only to passes explicitly requiring the corridor."""
    from contextlib import ExitStack
    from dgloss import pipeline, pad_terminals
    run = pipeline._run_optimization_pass
    def wrapped(results, context, selected, *args, **kwargs):
        previous = getattr(context, '_reduction_motion', None)
        context._reduction_motion = motion if selected.stay_in_corridor else None
        try:
            return run(results, context, selected, *args, **kwargs)
        finally:
            context._reduction_motion = previous
    with ExitStack() as stack:
        stack.enter_context(patch.object(pipeline, '_run_optimization_pass', wrapped))
        if early_pad:
            stack.enter_context(patch.object(pad_terminals, '_best_pad_connector', streaming_pad))
        yield


def streaming_pad(context, pad, chain, points, outside, net_vias, foreign,
                  deadline=None, stay_in_corridor=False, accept_replacement=None):
    """Certify each family's first valid contender before enumerating more.

    Families are monotone in length. Stop a family once it cannot beat the
    certified incumbent, and retain that incumbent on a budget interruption.
    """
    from dgloss import pad_terminals as p
    from net_queries import calculate_route_length
    from dgloss.krt_clearance import stable_copper_search
    @stable_copper_search
    def search(context):
        centre, anchor = (pad.global_x, pad.global_y), points[-1]
        old_length = calculate_route_length(chain)
        best, score = None, None
        for source, family in p._connector_families(centre, anchor, chain[0], context.coord.grid_step):
            for candidate in family:
                if deadline is not None and perf_counter() >= deadline:
                    return best
                length = calculate_route_length(candidate)
                candidate_score = length, len(candidate)
                if score is not None and candidate_score >= score:
                    break
                if old_length - length <= context.coord.grid_step + 1e-12:
                    break
                if not p._candidate_clearance(context, foreign, candidate, source, chain, defer_exact=True):
                    continue
                if (p._touches_other_same_net(candidate, outside, net_vias, (centre, anchor)) or
                        p._new_boundary_right_angle(candidate, anchor, outside)):
                    continue
                if not context.clearance_adapter.connector_clears(candidate):
                    continue
                if stay_in_corridor and not p.stays_in_corridor(context, points, candidate, deadline):
                    continue
                if accept_replacement is not None and not accept_replacement(chain, candidate):
                    continue
                best, score = candidate, candidate_score
                break
        return best
    return search(context)
