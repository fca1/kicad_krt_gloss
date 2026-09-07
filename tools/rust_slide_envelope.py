"""Shadow-only comparison of shifted swept envelopes on KRT's Rust grid.

No grid answer authorizes or rejects an optimization. The caller always keeps
the existing exact answer. Swept envelopes include endpoint tangential motion.
"""
from contextlib import contextmanager
from dataclasses import replace
from collections import defaultdict
import math
import sys
from time import perf_counter
from unittest.mock import patch

from dgloss.krt_api import Segment, _segment_fits_wide
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.segment_sliding import _joints_at_offset
import tools.adaptive_segment_slide as adaptive


def envelope(geometry, template, low, high, sign=1, centered=True):
    """Capsule containing the middle's affine sweep, in physical millimetres."""
    base = _joints_at_offset(geometry, 0.)
    unit = _joints_at_offset(geometry, 1.)
    speed = max(math.dist(a,b) for a,b in zip(base,unit))
    offset = (low+high)/2 if centered else low
    joints = _joints_at_offset(geometry, sign*offset)
    radius = (high-low)*speed*(.5 if centered else 1.)
    return Segment(*joints[0],*joints[1],template.width+2*radius,
                   template.layer,template.net_id)


class GridProbe:
    """Reuse one net-excluding map and rounded grid certificates per search."""
    def __init__(self, context, net_id):
        self.context=context
        self.obstacles=context.foreign_obstacles(net_id)
        self.margins={}
        self.cache={}
        self.calls=0
        self.hits=0

    def clears(self, segment):
        ctx=self.context
        layer=ctx.layer_map[segment.layer]
        width=segment.width
        if width not in self.margins:
            self.margins[width]=ctx.config.track_margins_for_width(width)
        margin=self.margins[width][layer]
        start=ctx.coord.to_grid(segment.start_x,segment.start_y)
        end=ctx.coord.to_grid(segment.end_x,segment.end_y)
        key=layer,start,end,margin
        if key in self.cache:
            self.hits+=1
            return self.cache[key]
        self.calls+=1
        result=_segment_fits_wide(segment,self.obstacles,ctx.coord,layer,margin)
        self.cache[key]=result
        return result


class Observer:
    def __init__(self):
        self.totals=defaultdict(lambda:dict(queries=0,seconds=0.,grid_clear=0,
            grid_clear_exact_blocked=0,grid_blocked_exact_clear=0,
            exact_seconds_on_grid_clear=0.,rust_calls=0,cache_hits=0))
        self.exact_seconds=0.
        self.map_seconds=0.
        self.offgrid=0
        self.queries=0
        self.disagreements=[]
        self.active=[]

    @contextmanager
    def activate(self):
        original_best=adaptive.best_slide
        exact=KrtClearanceAdapter.segment_clears
        def search(context,source,*args,**kwargs):
            self.active.append([context,source[0].net_id,None])
            try:return original_best(context,source,*args,**kwargs)
            finally:self.active.pop()
        def measured(adapter,segment):
            frame=sys._getframe(1)
            if (not self.active or frame.f_code.co_name!='sweep' or
                    frame.f_locals.get('i')!=1 or
                    segment.width<=frame.f_locals['source'][1].width+1e-9):
                return exact(adapter,segment)
            start=perf_counter();verdict=exact(adapter,segment)
            elapsed=perf_counter()-start
            self.exact_seconds+=elapsed;self.queries+=1
            active=self.active[-1];context=active[0]
            if active[2] is None:
                start=perf_counter()
                active[2]={name:GridProbe(context,active[1]) for name in
                           ('centered','initial','centered_snap_guard')}
                self.map_seconds+=perf_counter()-start
            coordinates=(segment.start_x,segment.start_y,segment.end_x,segment.end_y)
            if any(abs(v/context.coord.grid_step-round(v/context.coord.grid_step))>1e-6 for v in coordinates):
                self.offgrid+=1
            local=frame.f_locals
            shifted=envelope(local['geometry'],local['source'][1],local['left'],local['right'],local['sign'])
            # Reproduce the prototype's current envelope exactly before timing it.
            assert max(abs(a-b) for a,b in zip(coordinates,(shifted.start_x,shifted.start_y,shifted.end_x,shifted.end_y)))<1e-7
            assert abs(shifted.width-segment.width)<1e-7
            initial=envelope(local['geometry'],local['source'][1],local['left'],local['right'],local['sign'],False)
            # Endpoint snapping guard only; not a proof of raster/rule parity.
            guarded=replace(shifted,width=shifted.width+math.sqrt(2)*context.coord.grid_step)
            variants=[('centered',shifted),('initial',initial),('centered_snap_guard',guarded)]
            rotation=self.queries%3
            for label,candidate in variants[rotation:]+variants[:rotation]:
                probe=active[2][label]
                calls,hits=probe.calls,probe.hits
                start=perf_counter();free=probe.clears(candidate);duration=perf_counter()-start
                row=self.totals[label];row['queries']+=1;row['seconds']+=duration
                row['grid_clear']+=free
                row['grid_clear_exact_blocked']+=free and not verdict
                row['grid_blocked_exact_clear']+=not free and verdict
                row['exact_seconds_on_grid_clear']+=elapsed if free else 0.
                row['rust_calls']+=probe.calls-calls;row['cache_hits']+=probe.hits-hits
                if label=='centered' and free and not verdict and len(self.disagreements)<5:
                    self.disagreements.append(dict(coordinates=coordinates,width=segment.width,net=segment.net_id,layer=segment.layer))
            return verdict
        with patch.object(adaptive,'best_slide',search),patch.object(KrtClearanceAdapter,'segment_clears',measured):
            yield
