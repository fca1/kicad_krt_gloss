"""Search-local broad phase; exact same-net predicates stay in route_geometry.

Objects are immutable during a candidate search. Build a fresh view after a
replacement; there is no global cache or certificate shared across revisions.
"""
import math
import numpy as np

from .krt_api import pos_key


class SameNetSegments(tuple):
    """Ordered snapshot with a lazy, bounded grid of segment axis bounds."""

    _cell = 2.0
    _max_cells = 256

    def _window(self, x0, y0, x1, y1):
        return (math.floor(x0 / self._cell), math.floor(y0 / self._cell),
                math.floor(x1 / self._cell), math.floor(y1 / self._cell))

    def _build(self):
        grid, overflow = {}, []
        for index, seg in enumerate(self):
            coordinates = seg.start_x, seg.start_y, seg.end_x, seg.end_y
            if not all(map(math.isfinite, coordinates)):
                overflow.append(index)
                continue
            a, b, c, d = self._window(min(seg.start_x, seg.end_x),
                min(seg.start_y, seg.end_y), max(seg.start_x, seg.end_x),
                max(seg.start_y, seg.end_y))
            if (c - a + 1) * (d - b + 1) > self._max_cells:
                overflow.append(index)
                continue
            for x in range(a, c + 1):
                for y in range(b, d + 1):
                    grid.setdefault((seg.layer, x, y), []).append(index)
        self._grid, self._overflow = grid, overflow

    def _near_bounds(self, bounds, layer):
        """Vectorized fallback for wide queries and many long segments."""
        if not hasattr(self, '_boxes'):
            self._boxes = np.asarray([(min(s.start_x, s.end_x),
                min(s.start_y, s.end_y), max(s.start_x, s.end_x),
                max(s.start_y, s.end_y)) for s in self]).T
            self._finite = np.fromiter((all(map(math.isfinite,
                (s.start_x, s.start_y, s.end_x, s.end_y))) for s in self), bool)
            self._layers = {}
        if layer not in self._layers:
            self._layers[layer] = np.fromiter((s.layer == layer for s in self), bool)
        x0, y0, x1, y1 = bounds
        a, b, c, d = self._boxes
        near = self._layers[layer] & (~self._finite |
            ((c >= x0) & (a <= x1) & (d >= y0) & (b <= y1)))
        return (self[index] for index in np.flatnonzero(near))

    def at_endpoint(self, layer, key):
        """Use KRT's exact position key; preserve order and start/end precedence."""
        if not hasattr(self, '_endpoints'):
            endpoints = {}
            for seg in self:
                start = pos_key(seg.start_x, seg.start_y)
                end = pos_key(seg.end_x, seg.end_y)
                endpoints.setdefault((seg.layer, start), []).append(seg)
                if end != start:
                    endpoints.setdefault((seg.layer, end), []).append(seg)
            self._endpoints = endpoints
        return self._endpoints.get((layer, key), ())

    def near(self, seg):
        if len(self) < 16:
            return self
        if not all(map(math.isfinite, (seg.start_x, seg.start_y,
                                      seg.end_x, seg.end_y))):
            return self
        # Covers the 1e-7 mm collinearity tolerance, in either orientation.
        margin = 1e-6
        bounds = (
            math.nextafter(min(seg.start_x, seg.end_x) - margin, -math.inf),
            math.nextafter(min(seg.start_y, seg.end_y) - margin, -math.inf),
            math.nextafter(max(seg.start_x, seg.end_x) + margin, math.inf),
            math.nextafter(max(seg.start_y, seg.end_y) + margin, math.inf))
        if not all(map(math.isfinite, bounds)):
            return self
        a, b, c, d = self._window(*bounds)
        if (c - a + 1) * (d - b + 1) > self._max_cells:
            return self._near_bounds(bounds, seg.layer)
        if not hasattr(self, '_grid'):
            self._build()
        if len(self._overflow) > len(self) // 4:
            return self._near_bounds(bounds, seg.layer)
        indices = set(self._overflow)
        for x in range(a, c + 1):
            for y in range(b, d + 1):
                indices.update(self._grid.get((seg.layer, x, y), ()))
        return (self[index] for index in sorted(indices))
