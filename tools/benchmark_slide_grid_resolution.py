"""Shadow the same sliding envelopes on three KRT grid resolutions.

One optimization per board; grid answers never affect geometry. Timings include
Python wrappers/cache lookups, with actual native misses timed separately.
"""
import argparse
from collections import defaultdict
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import replace
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig, run_final_gloss
from dgloss.context import GlossContext, build_gloss_context
from dgloss.krt_api import _segment_fits_wide
from dgloss.krt_clearance import KrtClearanceAdapter
import tools.adaptive_segment_slide as adaptive


def counters():
    return dict(queries=0, seconds=0., native_seconds=0., calls=0, hits=0,
                free=0, free_exact_blocked=0, blocked_exact_free=0,
                exact_seconds_on_free=0., exact_seconds_on_agreeing_free=0.)


class ResolutionObserver:
    def __init__(self, steps):
        self.steps = steps
        self.contexts = {}
        self.active = []
        self.rows = defaultdict(counters)
        self.costs = {str(step): dict(build_seconds=0., update_seconds=0.,
                                    selection_seconds=0., builds=0, updates=0)
                      for step in steps}
        self.queries = 0
        self.exact_seconds = 0.

    def grids(self, context):
        if id(context) not in self.contexts:
            grids = {}
            for step in self.steps:
                started = perf_counter()
                grid = build_gloss_context(context.pcb_data,
                    replace(context.config, grid_step=step), context.net_ids)
                cost = self.costs[str(step)]
                cost['build_seconds'] += perf_counter() - started
                cost['builds'] += 1
                grids[step] = grid
            # Retain source identity to prevent id reuse between contexts.
            self.contexts[id(context)] = (context, grids)
        return self.contexts[id(context)][1]

    @contextmanager
    def activate(self):
        original_best = adaptive.best_slide
        original_exact = KrtClearanceAdapter.segment_clears
        original_refresh = GlossContext.refresh_net_obstacles

        def search(context, source, *args, **kwargs):
            self.active.append([context, source[0].net_id, None])
            try:
                return original_best(context, source, *args, **kwargs)
            finally:
                self.active.pop()

        def refresh(context, net_id):
            result = original_refresh(context, net_id)
            if id(context) in self.contexts:
                for step, grid in self.contexts[id(context)][1].items():
                    started = perf_counter()
                    original_refresh(grid, net_id)
                    cost = self.costs[str(step)]
                    cost['update_seconds'] += perf_counter() - started
                    cost['updates'] += 1
            return result

        def measured(adapter, segment):
            frame = sys._getframe(1)
            if (not self.active or frame.f_code.co_name != 'sweep' or
                    frame.f_locals.get('i') != 1 or
                    segment.width <= frame.f_locals['source'][1].width + 1e-9):
                return original_exact(adapter, segment)
            started = perf_counter()
            verdict = original_exact(adapter, segment)
            exact_time = perf_counter() - started
            self.exact_seconds += exact_time
            self.queries += 1
            active = self.active[-1]
            if active[2] is None:
                active[2] = {}
                for step, grid in self.grids(active[0]).items():
                    started = perf_counter()
                    obstacles = grid.foreign_obstacles(active[1])
                    self.costs[str(step)]['selection_seconds'] += perf_counter() - started
                    active[2][step] = (grid, obstacles, {}, {})
            variants = [(step, guard) for step in self.steps for guard in (False, True)]
            rotation = self.queries % len(variants)
            for step, guard in variants[rotation:] + variants[:rotation]:
                grid, obstacles, margins, caches = active[2][step]
                row = self.rows[f'{step}/{"guard" if guard else "plain"}']
                started = perf_counter()
                candidate = replace(segment, width=segment.width + math.sqrt(2)*step) if guard else segment
                layer = grid.layer_map[candidate.layer]
                if candidate.width not in margins:
                    margins[candidate.width] = grid.config.track_margins_for_width(candidate.width)
                margin = margins[candidate.width][layer]
                key = (layer, grid.coord.to_grid(candidate.start_x, candidate.start_y),
                       grid.coord.to_grid(candidate.end_x, candidate.end_y), margin)
                cache = caches.setdefault(guard, {})
                if key in cache:
                    free = cache[key]
                    row['hits'] += 1
                else:
                    native_start = perf_counter()
                    free = _segment_fits_wide(candidate, obstacles, grid.coord, layer, margin)
                    row['native_seconds'] += perf_counter() - native_start
                    cache[key] = free
                    row['calls'] += 1
                row['seconds'] += perf_counter() - started
                row['queries'] += 1
                row['free'] += bool(free)
                row['free_exact_blocked'] += bool(free and not verdict)
                row['blocked_exact_free'] += bool(not free and verdict)
                row['exact_seconds_on_free'] += exact_time if free else 0.
                row['exact_seconds_on_agreeing_free'] += exact_time if free and verdict else 0.
            return verdict

        with patch.object(adaptive, 'best_slide', search), \
             patch.object(KrtClearanceAdapter, 'segment_clears', measured), \
             patch.object(GlossContext, 'refresh_net_obstacles', refresh):
            yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    digest = hashlib.sha256(args.board.read_bytes()).hexdigest()
    observer = ResolutionObserver((.1, .05, .025))
    log = io.StringIO()
    with redirect_stdout(log), redirect_stderr(log):
        pcb = gloss.parse_kicad_pcb(str(args.board))
        ids = sorted({s.net_id for s in pcb.segments if s.net_id})
        options = gloss.build_parser().parse_args([str(args.board), '--preview'])
        config = gloss.build_krt_config(options, pcb, ids)
        with observer.activate(), adaptive.activate(adaptive.SearchStats()):
            outcome = run_final_gloss([], pcb, config,
                GlossConfig(stay_in_corridor=True, budget_seconds=1200), net_ids=ids)
    assert hashlib.sha256(args.board.read_bytes()).hexdigest() == digest
    data = dict(board=str(args.board), sha256=digest, source_unchanged=True,
        protocol='one instrumented run; identical envelopes and board revisions for all grids; no grid verdict used for acceptance; 1200s instrumentation budget; per-search caches; timings are single samples',
        queries=observer.queries, exact_seconds=observer.exact_seconds,
        costs=observer.costs, rows=dict(observer.rows), stats=outcome.stats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k != 'stats'}, indent=2))
    print('gain', outcome.stats.get('saved_mm'), 'G5', outcome.stats.get('g5_valid'),
          'stop', outcome.stats.get('g4_stop_reason'), flush=True)


if __name__ == '__main__':
    main()
