"""A/B harness retaining the pre-integration pad search for historical comparison.

Production uses dgloss.reduction_motion and pad_terminals directly. Only tests
and benchmarks may patch the policy through this module.
"""
from contextlib import contextmanager, ExitStack
from unittest.mock import patch
from dgloss.execution import perf_counter
from dgloss.krt_api import calculate_route_length
from dgloss.krt_clearance import stable_copper_search
from dgloss.reduction_motion import MotionCertificate
from dgloss import pad_terminals as p
from dgloss.pad_terminals import _best_pad_connector as streaming_pad


@stable_copper_search
def _legacy_pad_connector(context, pad, chain, points, outside, net_vias,
                        foreign, deadline=None, stay_in_corridor=False,
                        accept_replacement=None):
    centre = (pad.global_x, pad.global_y)
    anchor = points[-1]
    old_length = calculate_route_length(chain)
    families = p._connector_families(centre, anchor, chain[0],
                                   context.coord.grid_step)
    candidates = []
    sequence = 0
    for source, family in families:
        if deadline is not None and perf_counter() >= deadline:
            break
        for candidate in family:
            if deadline is not None and perf_counter() >= deadline:
                break
            new_length = calculate_route_length(candidate)
            if old_length - new_length <= context.coord.grid_step + 1e-12:
                continue
            clearance = p._candidate_clearance(
                context, foreign, candidate, source, chain,
                defer_exact=True)
            if not clearance:
                continue
            if p._touches_other_same_net(candidate, outside, net_vias,
                                       (centre, anchor)):
                continue
            if p._new_boundary_right_angle(candidate, anchor, outside):
                continue
            score = (new_length, len(candidate))
            candidates.append((score, sequence, candidate,
                               clearance.exact_segment_ids))
            sequence += 1

    # Exact KRT geometry is authoritative, but only candidates competitive on
    # length reach it.  A rejected winner advances to the next-best candidate.
    for _score, _sequence, candidate, exact_segment_ids in sorted(candidates):
        if deadline is not None and perf_counter() >= deadline:
            break
        if (all(id(segment) in exact_segment_ids for segment in candidate) or
                context.clearance_adapter.connector_clears(candidate)):
            if not stay_in_corridor or p.stays_in_corridor(
                    context, points, candidate, deadline):
                if accept_replacement is None or accept_replacement(chain, candidate):
                    return candidate
    return None


@contextmanager
def activate(motion=None, early_pad=False):
    from dgloss import pipeline
    def configure(context, selected):
        context._reduction_motion = motion if selected.stay_in_corridor else None
    with ExitStack() as stack:
        stack.enter_context(patch.object(pipeline, '_configure_motion', configure))
        stack.enter_context(patch.object(p, '_best_pad_connector',
                                        streaming_pad if early_pad else _legacy_pad_connector))
        yield
