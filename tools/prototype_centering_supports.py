"""Isolated support-preserving Centering experiment; never saves the source PCB.

Run with KiCad Python. No production entry point imports this module.
Unconstrained supports remain fixed; infeasible intersections are rejected.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def solve_supports(points, constraints):
    """Intersect original oriented supports, replacing constrained line positions.

    constraints contains (segment index, point on required support). There are
    no passage lengths, search bands or preferred horizontal/vertical axes.
    """
    from dgloss.interpad_geometry import _native_direction, _line_intersection
    directions = [_native_direction(a, b) for a, b in zip(points, points[1:])]
    if not all(directions):
        return None
    origins = list(points[:-1])
    assigned = {}
    for index, axis in constraints:
        direction = directions[index]
        if index in assigned:
            delta = tuple(axis[k] - assigned[index][k] for k in (0, 1))
            if abs(delta[0]*direction[1] - delta[1]*direction[0]) > 1e-7:
                return None
        assigned[index] = axis
        origins[index] = axis
    for index, anchor in ((0, points[0]), (len(directions)-1, points[-1])):
        delta = tuple(anchor[k]-origins[index][k] for k in (0, 1))
        if abs(delta[0]*directions[index][1]-delta[1]*directions[index][0]) > 1e-7:
            return None
    built = [points[0]]
    for index in range(1, len(directions)):
        joint = _line_intersection(origins[index-1], directions[index-1],
                                   origins[index], directions[index])
        if joint is None:
            return None  # Parallel supports need a separate, explicit policy.
        built.append(joint)
    built.append(points[-1])
    for a, b, direction in zip(built, built[1:], directions):
        if sum((b[k]-a[k])*direction[k] for k in (0, 1)) <= 1e-7:
            return None
    return built


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


def winding(points, center):
    return round(sum(math.atan2(
        (a[0]-center[0])*(b[1]-center[1])-(a[1]-center[1])*(b[0]-center[0]),
        (a[0]-center[0])*(b[0]-center[0])+(a[1]-center[1])*(b[1]-center[1]))
        for a, b in zip(points, points[1:]+points[:1]))/(2*math.pi))


def main():
    from tools import reproduce_corridor_fold as native
    from dgloss import pipeline
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--net-id', type=int, default=7)
    args = parser.parse_args()
    fingerprint = hashlib.sha256(args.board.read_bytes()).hexdigest()
    board = native.pcbnew.LoadBoard(str(args.board.resolve()))
    pcb = native.build_pcb_data_from_board(board)
    config = native.build_krt_config(board, pcb, .1, net_ids={args.net_id})
    audit, results = [], []
    with ExitStack() as stack:
        stack.enter_context(patch('dgloss.protected_centering.build_protected_path',
            lambda context, doors, deadline=None: build_candidate(context, doors, deadline, audit=audit)))
        # No fallback to production constructors when this experiment rejects.
        stack.enter_context(patch('dgloss.interpad._centering_proposals', return_value=iter(())))
        stack.enter_context(patch('dgloss.interpad_paths.center_with_propagated_neighbors', return_value=iter(())))
        outcome = pipeline.run_centering(results, pcb, config, net_ids=[args.net_id],
                                         proximity_mm=2.54, _emit_log=False)
    applied = native.apply_gloss(board, results, outcome) if outcome.stats.get('g5_valid') else None
    if applied:
        from dgloss.interpad_geometry import _native_direction
        from dgloss.interpad import find_interpad_doors
        reread = native.build_pcb_data_from_board(board)
        scan = find_interpad_doors(reread, config, net_id=args.net_id, proximity_mm=2.54)
        assert len(scan.doors) == 3
        assert all(abs(door.offset) <= 1e-7 for door in scan.doors)
        for record in audit:
            old, new = record['before'], record['after']
            expected = [_native_direction(a, b) for a, b in zip(old, old[1:])]
            assert expected == [_native_direction(a, b) for a, b in zip(new, new[1:])]
            assert old[0] == new[0] and old[-1] == new[-1]
            changed_winding = [pad for pads in pcb.pads_by_net.values() for pad in pads
                               if pad.net_id != args.net_id and
                               winding(old+list(reversed(new)), (pad.global_x, pad.global_y)) != 0]
            assert not changed_winding
            # Check native copper, not just the floating-point candidate.
            for a, b in zip(new, new[1:]):
                assert any(s.net_id == args.net_id and
                           min(math.dist(a, (s.start_x, s.start_y))+math.dist(b, (s.end_x, s.end_y)),
                               math.dist(b, (s.start_x, s.start_y))+math.dist(a, (s.end_x, s.end_y))) <= 2e-6
                           for s in reread.segments)
        audit.append({'native_doors_centered': len(scan.doors),
                      'native_copper_matches': True, 'foreign_pad_winding_changes': 0,
                      'direction_sequence_preserved': True})
    assert hashlib.sha256(args.board.read_bytes()).hexdigest() == fingerprint
    print(json.dumps({'sha256': fingerprint, 'stats': outcome.stats,
                      'native_apply': applied, 'audit': audit}, indent=2, default=str))


if __name__ == '__main__':
    main()
