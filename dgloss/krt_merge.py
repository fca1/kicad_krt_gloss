"""Accept KRT merge proposals only when they really preserve copper/topology."""
from copy import copy
import math
from .krt_api import FP_EPS_MM
from .route_geometry import _octolinear_points
from .topology import ReplacementGuard
from .changes import release_result_custody


def same_copper_support(first, second):
    """Prove bidirectional interval coverage at identical layer/net/width.

    No rounded adjacency key or 'geometry_preserving' label is a proof.
    """
    def covered(source, target):
        for seg in source:
            dx, dy = seg.end_x-seg.start_x, seg.end_y-seg.start_y
            length = math.hypot(dx, dy)
            if length <= FP_EPS_MM:
                return False
            ux, uy = dx/length, dy/length
            intervals = []
            for other in target:
                if (seg.layer, seg.net_id, seg.width) != (other.layer, other.net_id, other.width):
                    continue
                offsets = [(other.start_x-seg.start_x, other.start_y-seg.start_y),
                           (other.end_x-seg.start_x, other.end_y-seg.start_y)]
                if all(abs(x*uy-y*ux) <= FP_EPS_MM for x, y in offsets):
                    intervals.append(sorted(x*ux+y*uy for x, y in offsets))
            cursor = 0.
            for low, high in sorted(intervals):
                if low > cursor+FP_EPS_MM:
                    break
                cursor = max(cursor, high)
            if cursor < length-FP_EPS_MM:
                return False
        return True
    return bool(first and second) and covered(first, second) and covered(second, first)


def merge_in_scope(results, context, net_ids, propose):
    pcb = context.pcb_data
    scope = set(net_ids)
    before = [s for s in pcb.segments if s.net_id in scope and
              (not context.branch_scoped or id(s) in context.editable_segment_ids)]
    trial = copy(pcb)
    trial.segments = list(pcb.segments)
    scratch = [{'new_segments': before, 'new_vias': []}]
    _, _, _, proposed, stats = propose(
        scratch, trial, scope, keep_input_copper=True, max_deviation=FP_EPS_MM,
        max_net_segs=len(pcb.segments)+1, max_chain_segs=len(pcb.segments)+1)
    remaining = {id(s) for s in trial.segments}
    removed = [s for s in before if id(s) not in remaining]
    accepted_old, accepted_new, rejected = [], [], []
    changed_nets = 0
    for net_id in sorted({s.net_id for s in removed}):
        old = [s for s in removed if s.net_id == net_id]
        new = [s for s in proposed if s.net_id == net_id]
        reason = None
        if not all(_octolinear_points((s.start_x, s.start_y), (s.end_x, s.end_y)) for s in new):
            reason = 'non_octolinear'
        elif not same_copper_support(old, new):
            reason = 'copper_changed'
        else:
            guard = ReplacementGuard(pcb, net_id,
                [s for s in pcb.segments if s.net_id == net_id],
                [v for v in pcb.vias if v.net_id == net_id])
            if not guard(old, new):
                reason = 'connectivity_changed'
        if reason:
            rejected.append({'net_id': net_id, 'reason': reason})
            continue
        changed_nets += 1
        accepted_old.extend(old)
        accepted_new.extend(new)
    native, _ = release_result_custody(results, accepted_old)
    if accepted_new:
        results.append({'new_segments': accepted_new, 'new_vias': [],
                        'cleanup': 'track_gloss_g3_5_segments'})
        context.apply_replacement(accepted_old, accepted_new)
    stats = dict(stats, joints=len(accepted_old)-len(accepted_new),
                 segs_removed=len(accepted_old), segs_added=len(accepted_new),
                 rejections=rejected, rejected_nets=len(rejected))
    return stats['joints'], changed_nets, native, accepted_new, stats
