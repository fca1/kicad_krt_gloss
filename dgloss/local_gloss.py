"""Single-direction local shortening with a continuous corridor certificate."""
import math

from .execution import perf_counter
from .corridor import stays_in_corridor
from .segment_sliding import slide_interval, slide_segment
from .topology import ReplacementGuard
from .krt_clearance import stable_copper_search
from .local_candidates import micro_free_candidates
from dgloss.krt_api import calculate_route_length


@stable_copper_search
def local_replacement(context, chain, net_id, current, vias, deadline=None):
    from .route_geometry import (_candidate_segments, _touches_other_same_net, _pad_holds_point, _octolinear_points)
    original = list(chain.segments)
    segments = list(original)
    points = list(chain.points)
    pads = context.pcb_data.pads_by_net.get(net_id, [])
    if (not any(_pad_holds_point(p, points[0], chain.layer, chain.width / 2) for p in pads)
            and any(_pad_holds_point(p, points[-1], chain.layer, chain.width / 2) for p in pads)):
        points.reverse()
        segments.reverse()
    original_ids = {id(s) for s in original}
    fixed = [s for s in current if id(s) not in original_ids]
    changed = False
    i = 0
    while i < len(segments) - 1:
        if deadline is not None and perf_counter() >= deadline:
            break
        accepted = None
        for size in (2, 3):
            source = segments[i:i + size]
            if len(source) != size:
                continue
            source_points = points[i:i + size + 1]
            candidates = list(_candidate_segments(source_points[0], source_points[-1],
                                                 chain.layer, chain.width, net_id))
            if size == 3:
                interval = slide_interval(*source)
                if interval:
                    for offset in (interval.minimum, interval.maximum):
                        if math.isfinite(offset):
                            slide = slide_segment(*source, offset)
                            if slide:
                                candidates.append([s for s in slide.segments
                                                   if calculate_route_length([s]) > 1e-7])
            outside = fixed + segments[:i] + segments[i + size:]
            guard = ReplacementGuard(context.pcb_data, net_id, fixed + segments, vias)
            candidates = [repaired for candidate in candidates
                          for repaired in micro_free_candidates(
                              candidate, context.coord.grid_step)]
            for candidate in sorted(candidates, key=calculate_route_length):
                if deadline is not None and perf_counter() >= deadline:
                    break
                if not all(_octolinear_points((s.start_x, s.start_y), (s.end_x, s.end_y))
                           for s in candidate):
                    continue
                gain = calculate_route_length(source) - calculate_route_length(candidate)
                if gain <= 1e-7 and not (abs(gain) <= 1e-7 and len(candidate) < size):
                    continue
                if (_touches_other_same_net(candidate, outside, vias,
                                            (source_points[0], source_points[-1])) or
                        not context.clearance_adapter.connector_clears(candidate) or
                        not stays_in_corridor(context, source_points, candidate, deadline) or
                        not guard(source, candidate)):
                    continue
                accepted = size, candidate
                break
            if accepted:
                break
        if accepted:
            size, candidate = accepted
            segments[i:i + size] = candidate
            points[i:i + size + 1] = [(candidate[0].start_x, candidate[0].start_y)] + [
                (s.end_x, s.end_y) for s in candidate]
            changed = True
            i = 0
        else:
            i += 1
    if changed:
        final_ids = {id(s) for s in segments}
        return ([s for s in original if id(s) not in final_ids],
                [s for s in segments if id(s) not in original_ids])
    return None
