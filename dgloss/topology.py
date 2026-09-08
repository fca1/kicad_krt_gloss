"""Local electrical certificates using the same KRT graph as final validation."""

from dgloss.krt_api import check_net_connectivity as _check
from dgloss.krt_api import UnionFind
from .zone_models import prepare_zone_models


def terminal_partition(grade):
    """Compare terminal identities, independently of KRT graph node numbering."""
    graph = grade.get("graph") or {}
    groups = {}
    if graph:
        union = UnionFind()
        for first, second in graph.get("edges", ()):
            union.union(first, second)
        for kind, key in (("pad", "pad_index_repr"),
                          ("zone", "zone_index_repr")):
            for index, point in (graph.get(key) or {}).items():
                groups.setdefault(union.find(point), set()).add((kind, index))
    else:
        for pad, component in (grade.get("pad_components") or {}).items():
            groups.setdefault(component, set()).add(pad)
    return frozenset(frozenset(group) for group in groups.values())


def check_local_connectivity(net_id, segments, vias, pads, zones, *, pcb_data):
    # Use the loaded KRT zone model, just like final certification. This is an
    # electrical graph check, not a substitute for a native zone refill/DRC.
    zones = [zone for zone in (getattr(pcb_data, "zones", None) or [])
             if zone.net_id == net_id]
    prepare_zone_models(pcb_data, zones)
    return _check(net_id, segments, vias, pads, zones, pcb_data=pcb_data,
                  return_graph=True)


def reference_connectivity(pcb_data, net_id, segments, vias):
    """Reuse only the current reference graph; trial/final checks stay fresh."""
    cache = getattr(pcb_data, '_gloss_reference_grades', None)
    if cache is None:
        cache = pcb_data._gloss_reference_grades = {}
    key = tuple(map(id, segments)), tuple(map(id, vias))
    found = cache.get(net_id)
    if found is not None and found[0] == key:
        return found[1]
    grade = check_local_connectivity(net_id, segments, vias,
        pcb_data.pads_by_net.get(net_id, []), [], pcb_data=pcb_data)
    # Retain source objects so identities cannot be recycled under this key.
    cache[net_id] = key, grade, tuple(segments), tuple(vias)
    return grade


class ReplacementGuard:
    """Compute the baseline only if a geometrically valid contender reaches us."""

    def __init__(self, pcb_data, net_id, segments, vias):
        self.pcb_data = pcb_data
        self.net_id = net_id
        self.segments = segments
        self.vias = vias
        self.before = None
        self.last_trial = None
        self.last_result = None

    def __call__(self, removed, added):

        pads = self.pcb_data.pads_by_net.get(self.net_id, [])
        if self.before is None:
            self.before = reference_connectivity(
                self.pcb_data, self.net_id, self.segments, self.vias)
        removed_ids = {id(segment) for segment in removed}
        trial = [segment for segment in self.segments
                 if id(segment) not in removed_ids] + added
        if (self.last_trial is not None and len(trial) == len(self.last_trial) and
                all(first is second for first, second in zip(trial, self.last_trial))):
            return self.last_result
        after = check_local_connectivity(
            self.net_id, trial, self.vias, pads, [], pcb_data=self.pcb_data)
        self.last_trial = trial  # retain objects, preventing identity reuse
        self.last_result = not _connectivity_worse(self.before, after)
        return self.last_result


def _connectivity_worse(before, after):
    """Use KRT's connectivity grade without requiring an initially clean net."""
    if (before.get("graph") is not None and after.get("graph") is not None and
            terminal_partition(before) != terminal_partition(after)):
        return True
    return ((before.get("connected") and not after.get("connected")) or
            len(after.get("disconnected_pads") or []) >
            len(before.get("disconnected_pads") or []) or
            (after.get("num_components") or 1) >
            (before.get("num_components") or 1))
