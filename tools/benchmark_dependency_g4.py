"""One production-plus-worklist prototype run on the PACK0 tildagon board."""
import argparse
import hashlib
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig, run_final_gloss
from dgloss.krt_api import calculate_route_length
from tools.dependency_g4 import Controller


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budget', type=float, default=60.)
    parser.add_argument('--output', type=Path, default=Path('.build/dependency_g4_tildagon.json'))
    args = parser.parse_args()
    pack = json.loads(Path('docs/PACK0.json').read_text(encoding='utf-8'))
    entry = next(b for b in pack['boards'] if b['name'] == 'tildagon_base')
    board = Path(pack['corpus_root']) / entry['path']
    assert hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
    log = io.StringIO()
    controller = Controller(percent=1.)
    with redirect_stdout(log), redirect_stderr(log):
        pcb = gloss.parse_kicad_pcb(str(board))
        ids = sorted({s.net_id for s in pcb.segments if s.net_id})
        cli = gloss.build_parser().parse_args([str(board), '--preview'])
        config = gloss.build_krt_config(cli, pcb, ids)
        before = calculate_route_length(pcb.segments)
        with controller.activate():
            started = perf_counter()
            outcome = run_final_gloss([], pcb, config, GlossConfig(budget_seconds=args.budget), net_ids=ids)
            elapsed = perf_counter()-started
    assert hashlib.sha256(board.read_bytes()).hexdigest() == entry['sha256']
    data = dict(pack_id='PACK0', board=str(board), sha256=entry['sha256'],
        source_unchanged=True, seconds=elapsed,
        gain_mm=before-calculate_route_length(pcb.segments),
        budget_seconds=args.budget,
        protocol='single prototype run per budget, no repetition/warmup; production geometry; failed-certificate spatial worklist; full audit before convergence; 1 percent marginal gain threshold from total pass3; corridor=False; no Centering',
        dependencies=controller.dependencies.stats if controller.dependencies else {},
        stats=outcome.stats, log=log.getvalue().splitlines())
    path=args.output
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in ('stats','log')},indent=2))
    print('G5',outcome.stats.get('g5_valid'),'stop',outcome.stats.get('g4_stop_reason'))
    for row in outcome.stats.get('g4_passes',[]):
        print(row['total_pass'],row['direction'],len(row['net_ids']),row['saved_mm'],row['completed'])


if __name__ == '__main__':
    main()
