"""One A/B run per known board; no warm-up, repetition, or board write."""
import argparse
from contextlib import nullcontext, redirect_stdout, redirect_stderr
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig, run_final_gloss
from dgloss.krt_api import calculate_route_length
from tools.adaptive_segment_slide import SearchStats, activate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board',type=Path)
    parser.add_argument('--corridor',action='store_true')
    parser.add_argument('--budget',type=float,default=20.)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    digest = hashlib.sha256(args.board.read_bytes()).hexdigest()
    data = dict(board=str(args.board),sha256=digest,corridor=args.corridor,
                budget=args.budget,protocol='one run per variant, no warm-up',runs=[])
    for variant in ['current','adaptive']:
        log = io.StringIO()
        stats = SearchStats()
        with redirect_stdout(log), redirect_stderr(log):
            pcb = gloss.parse_kicad_pcb(str(args.board))
            ids = sorted({s.net_id for s in pcb.segments if s.net_id})
            options = gloss.build_parser().parse_args([str(args.board),'--preview'])
            config = gloss.build_krt_config(options,pcb,ids)
            before = calculate_route_length(pcb.segments)
            with activate(stats) if variant=='adaptive' else nullcontext():
                start = perf_counter()
                outcome = run_final_gloss([],pcb,config,GlossConfig(
                    stay_in_corridor=args.corridor,budget_seconds=args.budget),net_ids=ids)
                elapsed = perf_counter()-start
        counts = asdict(stats)
        counts.pop('offsets')
        row = dict(variant=variant,seconds=elapsed,gain_mm=before-calculate_route_length(pcb.segments),
                   segments=len(pcb.segments),search=counts,stats=outcome.stats,log=log.getvalue().splitlines())
        data['runs'].append(row)
        assert hashlib.sha256(args.board.read_bytes()).hexdigest()==digest
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
        print(variant,round(elapsed,3),'s',round(row['gain_mm'],4),'mm',
              'G5',outcome.stats.get('g5_valid'),'stop',outcome.stats.get('g4_stop_reason'),counts,flush=True)


if __name__=='__main__':
    main()
