"""Geometry signatures and final visual deltas, without copper mutation."""

from .changes import GlossChanges


def _route_signature(pcb_data, net_id):
    """Comparable routed-copper geometry for one net, without object IDs."""
    segments = []
    for segment in pcb_data.segments:
        if segment.net_id != net_id:
            continue
        start = (segment.start_x, segment.start_y)
        end = (segment.end_x, segment.end_y)
        segments.append((segment.layer, min(start, end), max(start, end),
                         segment.width, bool(getattr(segment, "graphic", False)),
                         bool(getattr(segment, "locked", False))))
    vias = []
    for via in pcb_data.vias:
        if via.net_id != net_id:
            continue
        vias.append((via.x, via.y, via.size, via.drill,
                     tuple(via.layers), bool(getattr(via, "free", False)),
                     bool(getattr(via, "locked", False)),
                     tuple(sorted((getattr(via, "tenting_attrs", {}) or {}).items()))))
    return tuple(sorted(segments)), tuple(sorted(vias))


def _final_visual_changes(baseline_segments, baseline_vias, pcb_data,
                          history):
    """Describe only the post-smooth to final delta, without intermediates."""
    final_segment_ids = {id(segment) for segment in pcb_data.segments}
    baseline_segment_ids = {id(segment) for segment in baseline_segments}
    segments = [
        {"old": segment, "stage": "Final"}
        for segment in baseline_segments if id(segment) not in final_segment_ids]
    segments.extend(
        {"new": segment, "stage": "Final"}
        for segment in pcb_data.segments
        if id(segment) not in baseline_segment_ids)

    roots = {}
    for entry in history.vias:
        old, new = entry.get("old"), entry.get("new")
        if old is None or new is None:
            continue
        root = roots.pop(id(old), old)
        roots[id(new)] = root
    final_via_ids = {id(via) for via in pcb_data.vias}
    vias = [{"old": old, "new": via, "stage": "Final"}
            for via in pcb_data.vias
            if id(via) in roots and id(via) in final_via_ids
            for old in [roots[id(via)]]]
    return GlossChanges(segments=segments, vias=vias,
                        doors=list(history.doors))
