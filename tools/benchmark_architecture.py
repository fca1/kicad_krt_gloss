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
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if args.engine_root:
        sys.path.insert(0, str(args.engine_root.resolve()))
    import gloss
    from dgloss import GlossConfig, run_final_gloss
    from dgloss.pipeline import _route_signature
    pack = json.loads((root / 'docs/PACK0.json').read_text())
    rows = []
    for entry in pack['boards']:
        if args.boards and entry['name'] not in args.boards:
            continue
        board = Path(pack['corpus_root']) / entry['path']
        assert hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
        with redirect_stdout(io.StringIO()):
            pcb = gloss.parse_kicad_pcb(str(board))
            ids = sorted({s.net_id for s in pcb.segments if s.net_id})
            cfg = gloss.build_krt_config(gloss.build_parser().parse_args(
                [str(board), '--preview']), pcb, ids)
            start = perf_counter()
            out = run_final_gloss([], pcb, cfg, GlossConfig(
                budget_seconds=args.budget, repeat_until_stable=True), net_ids=ids)
            elapsed = perf_counter() - start
        geometry = [_route_signature(pcb, net) for net in ids]
        row = dict(board=entry['name'], sha256=entry['sha256'], seconds=elapsed,
                   nets=out.stats.get('nets_processed', 0),
                   saved_mm=out.stats.get('saved_mm'), g5=out.stats.get('g5_valid'),
                   geometry_sha256=hashlib.sha256(json.dumps(geometry).encode()).hexdigest(),
                   budget_expired=out.stats.get('gloss', {}).get('budget_expired'),
                   g4_passes=out.stats.get('g4_passes_completed'),
                   failure_stats=out.stats if not out.stats.get('g5_valid') else None,
                   segments=len(pcb.segments), vias=len(pcb.vias))
        row['nets_per_second'] = row['nets'] / elapsed
        rows.append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, indent=2), encoding='utf-8')
        assert hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
