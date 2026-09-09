"""Experimental fixed-support Centering; not production-qualified."""
import math
from time import perf_counter

def solve_supports(points, constraints):
    from dgloss.interpad_geometry import _native_direction, _line_intersection
    directions = [_native_direction(a, b) for a, b in zip(points, points[1:])]
    if not directions or not all(directions):
        return None
    groups = []
    membership = []
    for i, direction in enumerate(directions):
        if not i or direction != directions[i-1]:
            groups.append([i])
        else:
            # Only consecutive, equally oriented supports can be shared.
            groups[-1].append(i)
        membership.append(len(groups)-1)
    origins = [points[group[0]] for group in groups]
    assigned = {}
    def cross(a, b):
        return a[0]*b[1]-a[1]*b[0]
    def delta(a, b):
        return a[0]-b[0], a[1]-b[1]
    for index, axis in constraints:
        group = membership[index]
        direction = directions[index]
        if group in assigned and abs(cross(delta(axis, assigned[group]), direction)) > 1e-7:
            return None
        assigned[group] = axis
        origins[group] = axis
    for i, anchor in ((0, points[0]), (len(directions)-1, points[-1])):
        if abs(cross(delta(anchor, origins[membership[i]]), directions[i])) > 1e-7:
            return None
    result = [points[0]]
    for i in range(1, len(directions)):
        left, right = membership[i-1], membership[i]
        if left == right:
            # Orthogonal projection preserves the original longitudinal joint;
            # no arbitrary split ratio, fusion or new connection is introduced.
            u = directions[i]
            normal = (-u[1], u[0])
            distance = sum(x*y for x, y in zip(delta(origins[right], points[i]), normal))
            scale = distance / sum(x*x for x in normal)
            joint = tuple(points[i][k]+scale*normal[k] for k in (0, 1))
        else:
            joint = _line_intersection(origins[left], directions[i-1], origins[right], directions[i])
            if joint is None:
                return None
        result.append(joint)
    result.append(points[-1])
    for a, b, direction in zip(result, result[1:], directions):
        if sum(x*y for x, y in zip(delta(b, a), direction)) <= 1e-7:
            return None
    return result



def build_candidate(context, doors, deadline=None, *, audit):
    from dgloss.chain_topology import _simple_chains
    from dgloss.interpad_types import InterpadCandidate
    from dgloss.route_geometry import _segments_for_points
    from dgloss.krt_api import calculate_route_length
    from dgloss.protected_centering import certify_passages
    if not doors:
        return None
    ids = {id(d.segment) for d in doors}
    chain = next((c for c in _simple_chains(context.pcb_data, doors[0].segment.net_id)
                  if ids <= {id(s) for s in c.segments}), None)
    if chain is None or not context.segments_editable(chain.segments):
        audit.append({'rejected': 'scope'})
        return None
    positions = {id(s): i for i, s in enumerate(chain.segments)}
    points = solve_supports(chain.points, [(positions[id(d.segment)], d.axis) for d in doors])
    if points is None:
        audit.append({'rejected': 'support constraints'})
        return None
    segments = _segments_for_points(points, chain.layer, chain.width, doors[0].segment.net_id)
    changed = [i for i in range(len(segments))
               if math.dist(points[i], chain.points[i]) > 1e-9 or
               math.dist(points[i+1], chain.points[i+1]) > 1e-9]
    if not changed:
        first, last = 0, len(segments)
    else:
        first, last = min(changed), max(changed)+1
    source = tuple(chain.segments[first:last])
    replacement = tuple(segments[first:last])
    candidate = InterpadCandidate(source, replacement, (0., 0.),
                                 calculate_route_length(source), calculate_route_length(replacement))
    record = {'before': list(chain.points), 'after': points, 'doors': len(doors),
              'length_delta': candidate.after_length-candidate.before_length,
              'replacement_range': [first, last]}
    audit.append(record)
    record['final_clearance_failures'] = [
        {'index': i, 'source_also_fails': not context.clearance_adapter.segment_clears(chain.segments[i])}
        for i, segment in enumerate(segments)
        if not context.clearance_adapter.segment_clears(segment)]
    if not certify_passages(candidate, doors):
        record['rejected'] = 'passages'
        return None
    # Actual corresponding vertices, not an arclength remapping. Each move
    # sweeps its two incident edges; KRT uses the physical copper width.
    current = list(chain.points)
    for index in range(1, len(points)-1):
        if deadline is not None and perf_counter() >= deadline:
            record['rejected'] = 'deadline'
            return None
        if math.dist(current[index], points[index]) <= 1e-9:
            continue
        for neighbor in (index-1, index+1):
            if not context.clearance_adapter.sweep_triangle_clears(
                    (current[neighbor], current[index], points[index]), chain.segments[0]):
                record['rejected'] = f'KRT sweep vertex {index}, neighbor {neighbor}'
                return None
        current[index] = points[index]
    record['foreign_obstacle_sweep'] = True
    return candidate
