"""One detached run per PACK0 board, with exact geometry signatures for comparison."""
import argparse
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from time import perf_counter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--boards', nargs='*')
    parser.add_argument('--budget', type=float, default=120.)
    parser.add_argument('--corridor', action='store_true')
    parser.add_argument('--details', action='store_true')
    parser.add_argument('--audit-clearance', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if args.engine_root:
        sys.path.insert(0, str(args.engine_root.resolve()))
    import gloss
    from dgloss import GlossConfig, run_final_gloss
    from dgloss.pipeline import _route_signature
    import dgloss
    print('ENGINE', dgloss.__file__, 'CORRIDOR', args.corridor, flush=True)
    pack = json.loads((root / 'docs/PACK0.json').read_text())
    rows = []
    failed = False
    for entry in pack['boards']:
        if args.boards and entry['name'] not in args.boards:
            continue
        board = Path(pack['corpus_root']) / entry['path']
        assert hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
        log = io.StringIO()
        with redirect_stdout(log):
            load_start = perf_counter()
            pcb = gloss.parse_kicad_pcb(str(board))
            ids = sorted({s.net_id for s in pcb.segments if s.net_id})
            cfg = gloss.build_krt_config(gloss.build_parser().parse_args(
                [str(board), '--preview']), pcb, ids)
            load_seconds = perf_counter() - load_start
            before_geometry = [_route_signature(pcb, net) for net in ids]
            original_ids = {id(s) for s in pcb.segments}
            start = perf_counter()
            out = run_final_gloss([], pcb, cfg, GlossConfig(
                budget_seconds=args.budget, repeat_until_stable=True,
                stay_in_corridor=args.corridor), net_ids=ids)
            elapsed = perf_counter() - start
        geometry = [_route_signature(pcb, net) for net in ids]
        row = dict(board=entry['name'], sha256=entry['sha256'], seconds=elapsed,
                   load_seconds=load_seconds, corridor=args.corridor,
                   budget_seconds=args.budget, grid_mm=cfg.grid_step,
                   before_geometry_sha256=hashlib.sha256(json.dumps(before_geometry).encode()).hexdigest(),
                   nets=out.stats.get('nets_processed', 0),
                   saved_mm=out.stats.get('saved_mm'), g5=out.stats.get('g5_valid'),
                   geometry_sha256=hashlib.sha256(json.dumps(geometry).encode()).hexdigest(),
                   budget_expired=out.stats.get('gloss', {}).get('budget_expired'),
                   g4_passes=out.stats.get('g4_passes_completed'),
                   connectivity_regressions=out.stats.get('connectivity_regressions'),
                   corridor_motion=out.stats.get('corridor_motion'),
                   log=log.getvalue().splitlines(),
                   failure_stats=out.stats if not out.stats.get('g5_valid') else None,
                   segments=len(pcb.segments), vias=len(pcb.vias))
        if args.details:
            import math
            def length(signature):
                return sum(math.dist(s[1], s[2]) for s in signature[0])
            row['per_net_geometry'] = [
                dict(net_id=net, label=pcb.nets[net].name,
                     before_mm=length(before), after_mm=length(after),
                     before=before, after=after)
                for net, before, after in zip(ids, before_geometry, geometry)]
        row['nets_per_second'] = row['nets'] / elapsed
        if args.audit_clearance:
            from dgloss.krt_clearance import KrtClearanceAdapter
            audit = KrtClearanceAdapter(pcb, cfg)
            row['clearance_audit'] = [dict(net=s.net_id,
                start=[s.start_x, s.start_y], end=[s.end_x, s.end_y],
                stages=[{k: v for k, v in e.items() if k != 'new'}
                        for e in out.changes.get('segments', []) if e.get('new') is s])
                for s in pcb.segments if id(s) not in original_ids and not audit.segment_clears(s)]
        row['input_unchanged'] = hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
        row['new_non_octolinear'] = sum(
            min(abs(s.end_x-s.start_x), abs(s.end_y-s.start_y),
                abs(abs(s.end_x-s.start_x)-abs(s.end_y-s.start_y))) > 1e-7
            for s in pcb.segments if id(s) not in original_ids)
        row['non_octolinear_details'] = [
            dict(net=s.net_id, start=[s.start_x, s.start_y], end=[s.end_x, s.end_y],
                 stages=[e for e in out.changes.get('segments', []) if e.get('new') is s])
            for s in pcb.segments if id(s) not in original_ids and
            min(abs(s.end_x-s.start_x), abs(s.end_y-s.start_y),
                abs(abs(s.end_x-s.start_x)-abs(s.end_y-s.start_y))) > 1e-7]
        for detail in row['non_octolinear_details']:
            detail['stages'] = [{k: v for k, v in e.items() if k != 'new'} for e in detail['stages']]
        failed |= not row['g5'] or not row['input_unchanged'] or bool(row['new_non_octolinear'])
        rows.append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, indent=2), encoding='utf-8')
        assert hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
        print(json.dumps(row), flush=True)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
