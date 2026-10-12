"""Remove a bend beside a free width transition without changing its widths.

The two outer supports meet at the proposed transition. Only a middle member
sharing one outer width may disappear. This is a finite local family, not a
general variable-width router; fixed pads, vias and branches remain anchors.
"""
from .execution import perf_counter
from .krt_api import Segment, FP_EPS_MM, calculate_route_length, point_in_polygon
from .krt_clearance import stable_copper_search
from .reduction_motion import graph, ends, MotionCertificate
from .route_geometry import (_line_intersection, _octolinear_points,
                             _segments_for_points, _touches_other_same_net)
from .sliding_nodes import _node_is_fixed
from .topology import ReplacementGuard


def _swept_same_net(polygons, outside, vias, anchors, template):
    for polygon in polygons:
        boundary = _segments_for_points(polygon + [polygon[0]], template.layer,
                                        template.width, template.net_id)
        if _touches_other_same_net(boundary, outside, vias, anchors):
            return True
        for segment in outside:
            if segment.layer == template.layer and any(
                    p not in anchors and point_in_polygon(*p, polygon)
                    for p in ends(segment)):
                return True
        if any((via.x, via.y) not in anchors and
               point_in_polygon(via.x, via.y, polygon) for via in vias):
            return True
    return False


@stable_copper_search
def transition_replacement(context, net_id, current, vias, deadline=None):
    """Return one certified replacement; the caller commits and revisits."""
    adjacency = graph(current)
    guard = ReplacementGuard(context.pcb_data, net_id, current, vias)
    for middle in current:
        if deadline is not None and perf_counter() >= deadline:
            return None
        b, c = ends(middle)
        if b == c or len(adjacency[b]) != 2 or len(adjacency[c]) != 2:
            continue
        first = next(s for s in adjacency[b] if s is not middle)
        last = next(s for s in adjacency[c] if s is not middle)
        source = [first, middle, last]
        if (first is last or first.width == last.width or
                middle.width not in (first.width, last.width) or
                not context.segments_editable(source) or
                any(s.layer != middle.layer or getattr(s, 'locked', False) or
                    getattr(s, 'graphic', False) for s in source)):
            continue
        if (_node_is_fixed(context.pcb_data, net_id, middle.layer, b, source[:2]) or
                _node_is_fixed(context.pcb_data, net_id, middle.layer, c, source[1:])):
            continue
        a = next(p for p in ends(first) if p != b)
        d = next(p for p in ends(last) if p != c)
        if not all(_octolinear_points(x, y) for x, y in zip((a, b, c), (b, c, d))):
            continue
        u, v = (b[0]-a[0], b[1]-a[1]), (c[0]-d[0], c[1]-d[1])
        joint = _line_intersection(a, u, d, v)
        if joint is None or any(
                (joint[0]-anchor[0])*direction[0] +
                (joint[1]-anchor[1])*direction[1] <= 0
                for anchor, direction in ((a, u), (d, v))):
            continue
        added = [Segment(*a, *joint, first.width, first.layer, net_id),
                 Segment(*joint, *d, last.width, last.layer, net_id)]
        if (min(calculate_route_length([s]) for s in added) < context.coord.grid_step or
                calculate_route_length(source)-calculate_route_length(added)
                <= context.coord.grid_step + FP_EPS_MM):
            continue
        outside = [s for s in current if all(s is not old for old in source)]
        if (_touches_other_same_net(added, outside, vias, (a, d)) or
                not context.clearance_adapter.connector_clears(added)):
            continue
        if middle.width == first.width:
            paths = [([a, b, c], [a, joint], first), ([d, c], [d, joint], last)]
        else:
            paths = [([a, b], [a, joint], first), ([d, c, b], [d, joint], last)]
        # Require a continuous certificate even with the optional corridor off.
        # The shared width transition moves together; each leg uses its own width.
        if any(_swept_same_net([old + list(reversed(new))], outside, vias,
                              (a, d), template) for old, new, template in paths):
            continue
        if (MotionCertificate().certify(context, paths, deadline=deadline) and
                guard(source, added)):
            return source, added
    return None
