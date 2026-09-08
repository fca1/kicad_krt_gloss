"""Bounded, opt-in local corridor experiment; never edits the input board."""
import sys
from pathlib import Path
from time import perf_counter
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss.algorithm import (_simple_chains, _candidate_segments,
                              _touches_other_same_net, _pad_holds_point)
from dgloss.context import build_gloss_context
from dgloss.corridor import stays_in_corridor
from dgloss.segment_sliding import slide_interval, slide_segment
from dgloss.topology import ReplacementGuard
from net_queries import calculate_route_length


def main():
    parser = gloss.build_parser()
    parser.add_argument('--bidirectional', action='store_true',
                        help='Alternate directions until both are stable.')
    args = parser.parse_args()
    pcb = gloss.parse_kicad_pcb(args.input_file)
    resolved = gloss.resolve_scope(parser, args, pcb)
    ids = [net_id for name, net_id in resolved]
    config = gloss.build_krt_config(args, pcb, ids)
    context = build_gloss_context(pcb, config, ids)
    start = perf_counter()
    deadline = start + args.budget_seconds
    original = list(pcb.segments)
    events = []
    tested = 0
    for net_id in ids:
        reverse = False
        stable_directions = 0
        while stable_directions < (2 if args.bidirectional else 1) and perf_counter() < deadline:
            again = False
            for chain in _simple_chains(pcb, net_id):
                pads = pcb.pads_by_net.get(net_id, [])
                if not any(_pad_holds_point(p, chain.points[0], chain.layer,
                                           chain.width / 2) for p in pads):
                    if any(_pad_holds_point(p, chain.points[-1], chain.layer,
                                           chain.width / 2) for p in pads):
                        chain.segments.reverse()
                        chain.points.reverse()
                if reverse:
                    chain.segments.reverse()
                    chain.points.reverse()
                for i in range(len(chain.segments) - 1):
                    if perf_counter() >= deadline:
                        break
                    accepted = None
                    for size in (2, 3):
                        source = chain.segments[i:i + size]
                        if len(source) != size:
                            continue
                        points = chain.points[i:i + size + 1]
                        old_length = calculate_route_length(source)
                        candidates = list(_candidate_segments(
                            points[0], points[-1], chain.layer, chain.width, net_id))
                        if size == 3:
                            interval = slide_interval(*source)
                            if interval:
                                for offset in (interval.minimum, interval.maximum):
                                    if not math.isfinite(offset):
                                        continue
                                    slid = slide_segment(*source, offset)
                                    if slid:
                                        candidates.append([s for s in slid.segments
                                                           if calculate_route_length([s]) > 1e-7])
                        current = [s for s in pcb.segments if s.net_id == net_id]
                        vias = [v for v in pcb.vias if v.net_id == net_id]
                        removed_ids = {id(s) for s in source}
                        outside = [s for s in current if id(s) not in removed_ids]
                        guard = ReplacementGuard(pcb, net_id, current, vias)
                        for candidate in sorted(candidates, key=calculate_route_length):
                            if perf_counter() >= deadline:
                                break
                            gain = old_length - calculate_route_length(candidate)
                            if gain <= 1e-7 and not (abs(gain) <= 1e-7 and len(candidate) < size):
                                continue
                            tested += 1
                            if (_touches_other_same_net(candidate, outside, vias,
                                                        (points[0], points[-1])) or
                                    not context.clearance_adapter.connector_clears(candidate) or
                                    not stays_in_corridor(context, points, candidate, deadline) or
                                    not guard(source, candidate)):
                                continue
                            accepted = source, candidate, gain, points
                            break
                        if accepted:
                            break
                    if accepted:
                        source, candidate, gain, points = accepted
                        removed_ids = {id(s) for s in source}
                        pcb.segments = [s for s in pcb.segments if id(s) not in removed_ids] + candidate
                        context.replace_editable_segments(source, candidate)
                        if hasattr(pcb, '_foreign_seg_arr_cache'):
                            pcb._foreign_seg_arr_cache = None
                        context.refresh_net_obstacles(net_id)
                        event = dict(index=len(events) + 1, start=points[0], end=points[-1],
                                     direction='reverse' if reverse else 'forward',
                                     before_segments=len(source), after_segments=len(candidate),
                                     gain_mm=round(gain, 6))
                        events.append(event)
                        print(event)
                        again = True
                        break
                if again:
                    break
            if again:
                stable_directions = 0
            else:
                stable_directions += 1
                reverse = not reverse
    before = [s for s in original if s.net_id in ids]
    after = [s for s in pcb.segments if s.net_id in ids]
    certified = all(ReplacementGuard(pcb, n, [s for s in original if s.net_id == n],
                                    [v for v in pcb.vias if v.net_id == n])(
                                        [s for s in original if s.net_id == n],
                                        [s for s in after if s.net_id == n]) for n in ids)
    print(dict(before_mm=calculate_route_length(before), after_mm=calculate_route_length(after),
               before_segments=len(before), after_segments=len(after), candidates=tested,
               steps=len(events), elapsed_ms=round((perf_counter()-start)*1000, 2),
               budget_expired=perf_counter() >= deadline, connectivity_valid=certified))
    assert certified
    if args.output_file and not args.preview:
        assert Path(args.input_file).resolve() != Path(args.output_file).resolve()
        original_ids = {id(s) for s in original}
        final_ids = {id(s) for s in pcb.segments}
        removed = [s for s in original if id(s) not in final_ids]
        added = [s for s in pcb.segments if id(s) not in original_ids]
        gloss.write_routed_output(args.input_file, args.output_file,
                                 [dict(new_segments=added, new_vias=[])], [], [], [], [], [], pcb,
                                 segments_to_remove=removed, vias_to_remove=[])


if __name__ == '__main__':
    main()
