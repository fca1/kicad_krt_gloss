"""Joint corridor certificate for mobile vias and T junctions.

Move shared vertices together and certify their actual triangular sweeps.
The via body follows its real copper and drill capsules, without inflation.
"""
from collections import defaultdict
from .execution import perf_counter

from .corridor import _parameterize, _at


def key(p):
    # A motion certificate must start at the actual copper, not at a rounded
    # graph representative. Near-coincident endpoints are not interchangeable.
    return tuple(p)


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
                          sweeps=0, via_sweeps=0, timed_out=0, seconds=0.)

    def certify(self, context, paths, old_via=None, new_via=None, deadline=None):
        started = perf_counter()
        try:
            return self._certify(context, paths, old_via, new_via, deadline)
        finally:
            self.stats['seconds'] += perf_counter() - started

    def _certify(self, context, paths, old_via, new_via, deadline):
        prepared = []
        for source, target, template in paths:
            if not source or not target:
                self.stats['rejected'] += 1
                return False
            old_knots = _parameterize(source) or [0., 1.]
            new_knots = _parameterize(target) or [0., 1.]
            knots = sorted(set(old_knots + new_knots))
            old = [_at(source, old_knots, k) for k in knots]
            new = [_at(target, new_knots, k) for k in knots]
            prepared.append((old, new, template))
        # Shared endpoints (via/T) must move together, never one leg at a time.
        # Equal source/target pairs define the same moving vertex. An edge
        # whose two vertices belong to the same group is a translating point.
        groups = {}
        for path_index, (old, new, template) in enumerate(prepared):
            for index, (a, b) in enumerate(zip(old, new)):
                groups.setdefault((a, b), []).append((path_index, index))
        with context.clearance_adapter.stable_copper():
            for (start, target), members in groups.items():
                if deadline is not None and perf_counter() >= deadline:
                    self.stats['timed_out'] += 1
                    self.stats['rejected'] += 1
                    return False
                if start == target:
                    continue
                for path_index, index in members:
                    old, new, template = prepared[path_index]
                    for neighbor in (index-1, index+1):
                        if 0 <= neighbor < len(old):
                            self.stats['sweeps'] += 1
                            if not context.clearance_adapter.sweep_triangle_clears(
                                    (old[neighbor], start, target), template):
                                self.stats['rejected'] += 1
                                return False
                for path_index, index in members:
                    prepared[path_index][0][index] = target
            if old_via is not None:
                self.stats['via_sweeps'] += 1
                if new_via is None or not context.clearance_adapter.via_sweep_clears(old_via, new_via):
                    self.stats['rejected'] += 1
                    return False
        if deadline is not None and perf_counter() >= deadline:
            self.stats['timed_out'] += 1
            self.stats['rejected'] += 1
            return False
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
