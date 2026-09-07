"""Opt-in segment-slide experiment; production dispatch is unchanged.

The length derivative selects one normal direction. Exponential expansion and
bisection search a certified connected prefix, never just clear endpoints.
Inconclusive swept envelopes are subdivided with a bounded KRT work budget.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass, field
import math
from unittest.mock import patch

from dgloss.execution import perf_counter
from dgloss.krt_api import Segment
from dgloss.segment_sliding import (
    _ordered_geometry, _joints_at_offset, _sub, _dot,
    slide_interval, slide_segment)


@dataclass
class SearchStats:
    searches: int = 0
    neutral: int = 0
    candidates: int = 0
    segment_probes: int = 0
    sweep_intervals: int = 0
    rejected: int = 0
    capped: int = 0
    seconds: float = 0.0
    offsets: list = field(default_factory=list)


def length_rate(geometry):
    """Exact affine length slope before any segment reverses direction."""
    a, b, c, d = geometry
    shifted = _joints_at_offset(geometry, 1.0)
    if shifted is None:
        return None
    vb, vc = _sub(shifted[0], b), _sub(shifted[1], c)
    rate = 0.0
    for vector, velocity in ((_sub(b, a), vb),
                             (_sub(c, b), _sub(vc, vb)),
                             (_sub(c, d), vc)):
        length = math.hypot(*vector)
        if length <= 1e-8:
            return None
        rate += _dot(vector, velocity) / length
    return rate


def best_slide(context, source, outside, vias, anchors, deadline=None, *,
               accept_replacement=None, stats=None, max_candidates=32,
               max_probes=512, stay_in_corridor=True):
    """Return only a shortening, certified incumbent; no geometry mutation."""
    from dgloss.algorithm import _touches_other_same_net
    stats = stats if stats is not None else SearchStats()
    stats.searches += 1
    started = perf_counter()
    probes_start = stats.segment_probes
    candidates_start = stats.candidates
    step = context.coord.grid_step
    tolerance = step / 4.0
    geometry = _ordered_geometry(*source)
    if geometry is None:
        return None
    rate = length_rate(geometry)
    if rate is None or abs(rate) < 1e-9:
        stats.neutral += 1
        return None
    sign = -1 if rate > 0 else 1
    interval = slide_interval(*source, minimum_length=step + 2e-6)
    if interval is None:
        return None
    limit = interval.maximum if sign > 0 else -interval.minimum
    if not math.isfinite(limit) or limit <= 0:
        return None
    a, b, c, d = geometry
    shifted = _joints_at_offset(geometry, 1.0)
    speeds = (0., math.dist(b, shifted[0]), math.dist(c, shifted[1]), 0.)

    def expired():
        return deadline is not None and perf_counter() >= deadline

    def sweep(low, high):
        stack = [(low, high, 0)]
        while stack:
            if expired() or stats.segment_probes - probes_start >= max_probes:
                return False
            left, right, depth = stack.pop()
            mid = (left + right) / 2
            joints = _joints_at_offset(geometry, sign * mid)
            points = (a, *joints, d)
            left_joints = _joints_at_offset(geometry, sign * left)
            right_joints = _joints_at_offset(geometry, sign * right)
            stats.sweep_intervals += 1
            clear = True
            for i in range(3):
                if expired() or stats.segment_probes - probes_start >= max_probes:
                    return False
                # Each outside member stays on one fixed support, so its swept
                # union is exactly its longest state, with no width inflation.
                if i in (0, 2):
                    fixed = a if i == 0 else d
                    joint = 0 if i == 0 else 1
                    far = max((left_joints[joint], right_joints[joint]),
                              key=lambda p: math.dist(fixed, p))
                    probe = Segment(*fixed, *far, source[i].width,
                                    source[i].layer, source[i].net_id)
                else:
                    # Every point of the moving middle is inside this capsule.
                    width = source[i].width + (right-left) * max(speeds[i:i+2])
                    probe = Segment(*points[i], *points[i+1], width,
                                    source[i].layer, source[i].net_id)
                stats.segment_probes += 1
                if not context.clearance_adapter.segment_clears(probe):
                    if i != 1:
                        return False  # Exact swept union already intersects.
                    if expired() or stats.segment_probes-probes_start >= max_probes:
                        return False
                    actual = Segment(*points[i], *points[i+1], source[i].width,
                                     source[i].layer, source[i].net_id)
                    stats.segment_probes += 1
                    if not context.clearance_adapter.segment_clears(actual):
                        return False  # A collision at the midpoint is decisive.
                    clear = False
                    break
            if not clear:
                if depth >= 10:
                    return False
                stack.extend(((mid, right, depth+1), (left, mid, depth+1)))
        return True

    def candidate_at(low, distance):
        stats.candidates += 1
        stats.offsets.append(sign * distance)
        slide = slide_segment(*source, sign * distance, minimum_length=step)
        if slide is None:
            return None
        segments = list(slide.segments)
        if _touches_other_same_net(segments, outside, vias, anchors):
            return None
        if stay_in_corridor and not sweep(low, distance):
            return None
        # Also check the rounded emitted geometry, independently of the sweep.
        for segment in segments:
            if expired() or stats.segment_probes - probes_start >= max_probes:
                return None
            stats.segment_probes += 1
            if not context.clearance_adapter.segment_clears(segment):
                return None
        if accept_replacement is not None and not accept_replacement(source, segments):
            return None
        return slide

    low, high, target, best = 0., None, min(step, limit), None
    try:
        with context.clearance_adapter.stable_copper():
            while not expired():
                if (stats.candidates-candidates_start >= max_candidates or
                        stats.segment_probes-probes_start >= max_probes):
                    stats.capped += 1
                    break
                candidate = candidate_at(low, target)
                if candidate is not None:
                    low = target
                    if candidate.before_length-candidate.after_length > 1e-7:
                        best = list(candidate.segments)
                    if limit-low <= tolerance:
                        break
                    target = min(limit, target*2) if high is None else (low+high)/2
                else:
                    stats.rejected += 1
                    high = target
                    target = (low+high)/2
                if high is not None and high-low <= tolerance:
                    break
        return best
    finally:
        stats.seconds += perf_counter() - started


@contextmanager
def activate(stats):
    """Test-only injection into both G3 callers; no runtime configuration flag."""
    from dgloss import algorithm, local_gloss
    from tools.adaptive_slide_local import local_replacement
    def reachable(context, source, outside, net_vias, anchors,
                  deadline=None, max_steps=2000):
        candidate = best_slide(context, source, outside, net_vias, anchors,
                               deadline, stats=stats)
        if candidate:
            yield candidate
    def local(*args, **kwargs):
        return local_replacement(*args, stats=stats, **kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch.object(algorithm, '_reachable_segment_slides', reachable))
        stack.enter_context(patch.object(local_gloss, 'local_replacement', local))
        yield
