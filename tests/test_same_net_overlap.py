"""Reject retraced copper even when its shared endpoint is allowed."""
import math

from dgloss.krt_api import Segment
from dgloss.route_geometry import _touches_other_same_net


def test_shared_endpoint_allows_join_but_not_positive_overlap():
    for angle in range(0, 360, 45):
        ux, uy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        def segment(a, b):
            return Segment(a * ux, a * uy, b * ux, b * uy, .2, 'F.Cu', 1)
        for reverse in (False, True):
            short = segment(1.41, 0) if reverse else segment(0, 1.41)
            assert _touches_other_same_net([short], [segment(0, 13.42)], [], [(0, 0)])
            assert not _touches_other_same_net([short], [segment(-3, 0)], [], [(0, 0)])
