"""Isolated collinear-support correction; production remains unchanged."""
import math


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
