"""Pass and final KRT certificates, independent of scheduling."""

import math
from .krt_api import check_net_connectivity, calculate_route_length
from .topology import terminal_partition as _terminal_partition
from .zone_models import prepare_zone_models
from .topology import _connectivity_worse


def _g5_grade(pcb_data, net_id):
    zones = [zone for zone in (getattr(pcb_data, "zones", None) or [])
             if zone.net_id == net_id]
    prepare_zone_models(pcb_data, zones)
    return check_net_connectivity(
        net_id,
        [segment for segment in pcb_data.segments if segment.net_id == net_id],
        [via for via in pcb_data.vias if via.net_id == net_id],
        pcb_data.pads_by_net.get(net_id, []), zones, pcb_data=pcb_data,
        return_graph=True)


def _validate_final(context, before_grades, before_length, changes, *, grade):
    """G3.5 safety gate retained by each internal G4 net call."""
    after_length = calculate_route_length(context.pcb_data.segments)
    if after_length > before_length + 1e-9:
        raise RuntimeError("G3.5 final length increased")
    for net_id, before in before_grades.items():
        after = grade(context.pcb_data, net_id)
        if _connectivity_worse(before, after):
            raise RuntimeError(f"G3.5 connectivity regression on net {net_id}")
    final_segment_ids = {id(segment)
                         for segment in context.pcb_data.segments}
    for entry in changes.segments:
        segment = entry.get("new")
        if segment is None or id(segment) not in final_segment_ids:
            continue
        if entry.get("geometry_preserving"):
            continue
        dx = abs(segment.end_x - segment.start_x)
        dy = abs(segment.end_y - segment.start_y)
        length = math.hypot(dx, dy)
        # Imported pad/track coordinates can differ by a few 1e-5 mm. This is
        # only a KRT-resolution classification tolerance, never a search step.
        tolerance = max(1e-7, context.coord.grid_step / 100.0)
        if not (dx <= tolerance or dy <= tolerance or
                abs(dx - dy) <= tolerance):
            raise RuntimeError("G3.5 produced non-octolinear copper")
        if length < context.coord.grid_step - 1e-9:
            raise RuntimeError("G3.5 produced a micro-segment")
    return after_length


def _certify_g5_copper(context, before_grades, changes, *, grade):
    """Recheck final changed copper with KRT; no geometry is generated here."""
    for net_id, before in before_grades.items():
        after = grade(context.pcb_data, net_id)
        if _terminal_partition(before) != _terminal_partition(after):
            raise RuntimeError(f"G5 topology changed on net {net_id}")

    final_segment_ids = {id(segment) for segment in context.pcb_data.segments}
    final_via_ids = {id(via) for via in context.pcb_data.vias}
    segment_ids = set()
    via_ids = set()
    preserved_segments = 0

    for entry in changes.segments:
        segment = entry.get("new")
        if (segment is None or id(segment) not in final_segment_ids or
                id(segment) in segment_ids):
            continue
        segment_ids.add(id(segment))
        if entry.get("geometry_preserving"):
            preserved_segments += 1
            continue
        if not context.clearance_adapter.segment_clears(segment):
            raise RuntimeError(
                f"G5 final copper clearance regression on net {segment.net_id}")

    via_attributes = ("size", "drill", "layers", "net_id", "free", "locked",
                      "tenting_attrs")
    for entry in changes.vias:
        old, via = entry.get("old"), entry.get("new")
        if (old is None or via is None or id(via) not in final_via_ids or
                id(via) in via_ids):
            continue
        via_ids.add(id(via))
        if any(getattr(old, name, None) != getattr(via, name, None)
               for name in via_attributes):
            raise RuntimeError(
                f"G5 moved-via attributes changed on net {via.net_id}")
        if not context.clearance_adapter.via_clears(via, ignored_via=via):
            raise RuntimeError(
                f"G5 final via clearance regression on net {via.net_id}")

    return {
        "segments_certified": len(segment_ids) - preserved_segments,
        "segments_geometry_preserved": preserved_segments,
        "vias_certified": len(via_ids),
    }
