"""Small opt-in contact prototype. Not connected to the Gloss pipeline.

KRT owns indexing and exact distances. A padded neighbourhood of KRT's
sampled cells is mandatory: get_nearby_segments alone ignores track width.
"""
import math
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()

from check_drc import SpatialIndex
from geometry_utils import segment_to_segment_distance_seg
from kicad_parser import Segment
from dgloss.algorithm import _touches_other_same_net


class ContactProbe:
    """Immutable, same-net outside-copper snapshot; rebuild after a change."""
    def __init__(self, outside):
        self.index = SpatialIndex()
        self.max_half_width = {}
        self.exact_calls = 0
        for seg in outside:
            self.index.add_segment(seg, seg.net_id)
            self.max_half_width[seg.layer] = max(
                self.max_half_width.get(seg.layer, 0.), seg.width / 2)

    def nearby(self, segment):
        radius = segment.width / 2 + self.max_half_width.get(segment.layer, 0.)
        # Each side's KRT cell walk may undersample by up to one cell.
        reach = math.ceil(radius / self.index.cell_size) + 2
        cells = self.index.cells_by_layer[segment.layer]
        seen, visited = set(), set()
        for cx, cy in self.index._get_segment_cells(segment):
            for dx in range(-reach, reach + 1):
                for dy in range(-reach, reach + 1):
                    key = cx + dx, cy + dy
                    if key in visited:
                        continue
                    visited.add(key)
                    for old, net in cells.get(key, ()):
                        if net == segment.net_id and id(old) not in seen:
                            seen.add(id(old))
                            yield old

    def rejects(self, candidate, anchors):
        for new in candidate:
            for old in self.nearby(new):
                radius = (new.width + old.width) / 2
                # Cheap bounds before KRT exact distance.
                if (max(new.start_x, new.end_x) + radius < min(old.start_x, old.end_x) or
                    max(old.start_x, old.end_x) + radius < min(new.start_x, new.end_x) or
                    max(new.start_y, new.end_y) + radius < min(old.start_y, old.end_y) or
                    max(old.start_y, old.end_y) + radius < min(new.start_y, new.end_y)):
                    continue
                self.exact_calls += 1
                if segment_to_segment_distance_seg(new, old) > radius + 1e-9:
                    continue
                shared = set(((new.start_x, new.start_y), (new.end_x, new.end_y))) & set(
                    ((old.start_x, old.start_y), (old.end_x, old.end_y)))
                if len(shared) != 1 or not shared.issubset(set(anchors)):
                    return True
                anchor = next(iter(shared))
                def ray(seg):
                    end = ((seg.end_x, seg.end_y) if
                           (seg.start_x, seg.start_y) == anchor else
                           (seg.start_x, seg.start_y))
                    return end[0] - anchor[0], end[1] - anchor[1]
                u, v = ray(new), ray(old)
                # A shared endpoint does not license a collinear overlap.
                if abs(u[0]*v[1] - u[1]*v[0]) <= 1e-9 and u[0]*v[0] + u[1]*v[1] > 0:
                    return True
        return False


def examples():
    def seg(a, b, width=.2, layer='F.Cu'):
        return Segment(*a, *b, width, layer, 1)
    candidate = [seg((0., 0.), (2., 0.))]
    anchors = [(0., 0.), (2., 0.)]
    return [
        ('copper_contact', candidate, [seg((1., .15), (1., 1.))], anchors, True),
        ('shared_overlap', candidate, [seg((0., 0.), (1., 0.))], anchors, True),
        ('T_anchor', candidate, [seg((0., 0.), (0., 1.))], anchors, False),
        ('straight_anchor', candidate, [seg((0., 0.), (-1., 0.))], anchors, False),
        ('clear_gap', candidate, [seg((1., .21), (1., 1.))], anchors, False),
        ('other_layer', candidate, [seg((1., .15), (1., 1.), layer='B.Cu')], anchors, False),
        ('cell_boundary', [seg((0., 1.95), (2., 1.95))],
         [seg((1., 2.05), (1., 3.))], [], True),
    ]


def measure(call, count=300):
    samples = []
    for _ in range(5):
        start = perf_counter()
        for _ in range(count):
            call()
        samples.append((perf_counter() - start) * 1e6 / count)
    return median(samples)


def main():
    for name, candidate, outside, anchors, expected in examples():
        probe = ContactProbe(outside)
        actual = probe.rejects(candidate, anchors)
        assert actual == expected, (name, actual, expected)
        calls = probe.exact_calls
        old = measure(lambda: _touches_other_same_net(candidate, outside, [], anchors))
        build = measure(lambda: ContactProbe(outside))
        query = measure(lambda: probe.rejects(candidate, anchors))
        print(f'{name}: OK; old={old:.2f} us; grid build={build:.2f} us; '
              f'query={query:.2f} us; exact pairs={calls}')


if __name__ == '__main__':
    main()
