"""Opt-in G4 worklist driven by failed KRT certificate regions.

The KRT SpatialIndex stores subscriptions, not clearance verdicts. Full audits
remain mandatory before convergence because not every rejection is observed.
"""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from time import perf_counter as wall_time

from dgloss.krt_api import SpatialIndex
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.search_cache import copper_box
import dgloss.pipeline as pipeline


def marginal_stop(total_pass, gain, previous_gain, percent=1.0):
    """Compare unrounded incremental gains; an undefined ratio never stops."""
    return (total_pass >= 3 and previous_gain > 1e-9 and
            gain <= previous_gain * percent / 100.0)


class Dependencies:
    def __init__(self, pcb, config, max_cells=4096):
        self.index = SpatialIndex(cell_size=2.0)
        self.layers = list(config.layers)
        self.max_cells = max_cells
        self.fallback = set()
        self.seen = set()
        self.margin = max([config.clearance, getattr(config, 'npth_clearance', 0.)] +
            [v for name in ('net_clearances', 'track_clearances', 'layer_clearances')
             for v in (getattr(config, name, None) or {}).values()])
        # Zone topology can change beyond the immediate edited region.
        self.zone_nets = {z.net_id for z in getattr(pcb, 'zones', ()) or ()}
        self.stats = dict(failed_queries=0, subscriptions=0, duplicates=0,
                          broad_fallbacks=0, seconds=0., notifications=0)

    def cells(self, box):
        x0, y0, x1, y1 = box
        a = self.index._get_cell(x0-self.margin, y0-self.margin)
        b = self.index._get_cell(x1+self.margin, y1+self.margin)
        if (b[0]-a[0]+1)*(b[1]-a[1]+1) > self.max_cells:
            return None
        return a, b

    def watch(self, item):
        started = wall_time()
        self.stats['failed_queries'] += 1
        bounds = self.cells(copper_box(item))
        if bounds is None:
            self.fallback.add(item.net_id)
            self.stats['broad_fallbacks'] += 1
        else:
            layers = [item.layer] if hasattr(item, 'layer') else self.layers
            a, b = bounds
            for layer in layers:
                key = item.net_id, layer, a, b
                if key in self.seen:
                    self.stats['duplicates'] += 1
                    continue
                self.seen.add(key)
                # Use KRT's box stamping through its pad-index API. The proxy
                # is only an index entry and never enters PCB geometry.
                box = copper_box(item)
                proxy = SimpleNamespace(global_x=(box[0]+box[2])/2,
                    global_y=(box[1]+box[3])/2,
                    size_x=box[2]-box[0]+2*self.margin,
                    size_y=box[3]-box[1]+2*self.margin)
                self.index.add_pad(proxy, item.net_id, [layer])
                self.stats['subscriptions'] += 1
        self.stats['seconds'] += wall_time()-started

    def affected(self, changes, eligible):
        started = wall_time()
        items = [item for group in (changes.segments, changes.vias)
                 for entry in group for key in ('old', 'new')
                 if (item := entry.get(key)) is not None]
        affected = set()
        if items:
            affected.update(self.fallback)
            affected.update(self.zone_nets)
        for item in items:
            affected.add(item.net_id)
            bounds = self.cells(copper_box(item))
            if bounds is None:
                affected.update(eligible)
                continue
            a, b = bounds
            layers = [item.layer] if hasattr(item, 'layer') else self.layers
            for layer in layers:
                cells = self.index.cells_by_layer[layer]
                for x in range(a[0], b[0]+1):
                    for y in range(a[1], b[1]+1):
                        affected.update(net for _, net in cells.get((x,y), ()))
        affected.intersection_update(eligible)
        self.stats['notifications'] += len(affected)
        self.stats['seconds'] += wall_time()-started
        return affected


class Controller:
    def __init__(self, percent=1.):
        self.percent = percent
        self.dependencies = None
        self.initial = None

    @contextmanager
    def activate(self):
        original_pass = pipeline._run_optimization_pass
        original_segment = KrtClearanceAdapter.segment_clears
        original_via = KrtClearanceAdapter.via_clears
        active = [False]

        def run_pass(results, context, config, net_ids, deadline, **kwargs):
            if self.dependencies is None:
                self.dependencies = Dependencies(context.pcb_data, context.config)
            active[0] = True
            try:
                outcome = original_pass(results, context, config, net_ids, deadline, **kwargs)
            finally:
                active[0] = False
            if self.initial is None:
                self.initial = outcome
            return outcome

        def segment(adapter, item):
            clear = original_segment(adapter, item)
            if active[0] and not clear:
                self.dependencies.watch(item)
            return clear

        def via(adapter, item, *args, **kwargs):
            clear = original_via(adapter, item, *args, **kwargs)
            if active[0] and not clear:
                self.dependencies.watch(item)
            return clear

        def multinet(*args, **kwargs):
            return run_worklist(*args, controller=self, **kwargs)

        with patch.object(pipeline, '_run_optimization_pass', run_pass), \
             patch.object(pipeline, 'run_multinet_passes', multinet), \
             patch.object(KrtClearanceAdapter, 'segment_clears', segment), \
             patch.object(KrtClearanceAdapter, 'via_clears', via):
            yield self


from dgloss.execution import perf_counter
from dgloss.krt_api import calculate_route_length
from dgloss.changes import GlossChanges
from dgloss.passes import _collect


def run_worklist(context, gloss_config, net_ids, results,
                        deadline, run_g3_5, *, controller):
    """Run affected-net waves, auditing all nets before declaring convergence."""
    pcb_data = context.pcb_data
    base_order = sorted(set(net_ids).intersection(context.net_ids))
    changes = GlossChanges()
    segment_strips = []
    via_strips = []
    changed_net_ids = set()
    passes = []
    operation_totals = {}
    total_changes = 0
    total_segment_reduction = 0
    started = perf_counter()
    pass_index = 0
    stop_reason = "converged"

    eligible = set(base_order)
    initial = controller.initial
    pending = controller.dependencies.affected(initial['changes'], eligible)
    pending.update(initial['changed_net_ids'])
    previous_gain = max(0., initial['before_length'] - initial['after_length'])
    while base_order:
        if perf_counter() >= deadline:
            stop_reason = "budget"
            break
        audit = not pending
        selected = eligible if audit else pending
        order = sorted(selected)
        if pass_index % 2:
            order.reverse()
        before = calculate_route_length(pcb_data.segments)
        pass_started = perf_counter()
        outcome = run_g3_5(
            results, context, gloss_config, order, deadline, emit_log=False)
        _collect(changes, outcome["changes"].as_dict(), pass_index + 2)
        for name in ("g3", "via", "pad", "node", "refine", "equal", "merge"):
            totals = operation_totals.setdefault(name, {})
            for key, value in outcome[name].items():
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0) + value
        merge_totals = operation_totals.setdefault("merge_summary", {})
        for key in ("merged_count", "merged_nets", "merge_ms"):
            merge_totals[key] = merge_totals.get(key, 0) + outcome[key]
        segment_strips.extend(outcome["segment_strips"])
        via_strips.extend(outcome["via_strips"])
        stage_rows = outcome["stage_stats"].as_dict()["stages"]
        pass_changes = sum(
            row.get("changes", 0) for stage, row in stage_rows.items()
            if stage not in ("G4", "G5"))
        pass_segment_reduction = (
            outcome["equal"]["segments_removed"] -
            outcome["equal"]["segments_added"] +
            outcome["merged_count"])
        changed_net_ids.update(outcome["changed_net_ids"])
        completed = perf_counter() < deadline
        if not completed:
            stop_reason = "budget"

        after = calculate_route_length(pcb_data.segments)
        elapsed_ms = (perf_counter() - pass_started) * 1000.0
        gain = max(0.0, before - after)
        passes.append({
            "index": pass_index + 1,
            "direction": "audit" if audit else "affected",
            "total_pass": pass_index + 2,
            "previous_gain_mm": previous_gain,
            "marginal_percent": (100*gain/previous_gain if previous_gain > 1e-9 else None),
            "net_ids": order,
            "changes": pass_changes,
            "segment_reduction": pass_segment_reduction,
            "saved_mm": round(gain, 4),
            "elapsed_ms": round(elapsed_ms, 3),
            "completed": completed,
            "operations": stage_rows,
        })
        print(f"Track Gloss G4 pass {pass_index + 1} "
              f"({'forward' if pass_index % 2 == 0 else 'reverse'}): "
              f"{pass_changes} transformations, "
              f"-{pass_segment_reduction} segments, -{gain:.4f} mm, "
              f"{elapsed_ms:.1f} ms")
        total_changes += pass_changes
        total_segment_reduction += pass_segment_reduction
        if not completed:
            break
        if pass_changes == 0 and audit:
            stop_reason = "converged"
            break
        if marginal_stop(pass_index + 2, gain, previous_gain, controller.percent):
            stop_reason = "marginal_gain"
            break
        pending = controller.dependencies.affected(outcome['changes'], eligible)
        pending.update(outcome['changed_net_ids'])
        if pass_changes == 0:
            pending.clear()  # a full audit must follow a quiet targeted wave
        previous_gain = gain
        pass_index += 1

    return {
        "segment_strips": segment_strips,
        "via_strips": via_strips,
        "changes": changes,
        "passes": passes,
        "operation_totals": operation_totals,
        "passes_completed": sum(row["completed"] for row in passes),
        "transformations": total_changes,
        "segment_reduction": total_segment_reduction,
        "net_ids_changed": changed_net_ids,
        "saved_mm": round(sum(row["saved_mm"] for row in passes), 4),
        "algorithm_ms": round((perf_counter() - started) * 1000.0, 3),
        "stop_reason": stop_reason,
    }
