"""Separate certificate-budget and failed-window-cache A/B experiments."""
import argparse
from contextlib import ExitStack,redirect_stdout,redirect_stderr
from dataclasses import asdict
import hashlib,io,json
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig,run_final_gloss
from dgloss.krt_api import calculate_route_length
import tools.adaptive_segment_slide as adaptive
from tools.slide_failure_cache import WindowCache,activate as activate_cache


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boards',nargs='+',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    data=dict(protocol='one run per board/variant; corridor=True; budget20s; baseline adaptive prototype; budget32 and cache never combined',runs=[],inputs={})
    variants=['reference','candidate_budget32','failure_cache']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for i,board in enumerate(args.boards):
        digest=hashlib.sha256(board.read_bytes()).hexdigest();data['inputs'][str(board)]=digest
        for variant in variants[i%3:]+variants[:i%3]:
            search=adaptive.SearchStats();cache=WindowCache();log=io.StringIO()
            with redirect_stdout(log),redirect_stderr(log):
                pcb=gloss.parse_kicad_pcb(str(board));ids=sorted({s.net_id for s in pcb.segments if s.net_id})
                options=gloss.build_parser().parse_args([str(board),'--preview'])
                config=gloss.build_krt_config(options,pcb,ids)
                before=calculate_route_length(pcb.segments)
                with ExitStack() as stack:
                    stack.enter_context(adaptive.activate(search))
                    if variant=='candidate_budget32':
                        original=adaptive.best_slide
                        def budgeted(*a,**kw):return original(*a,max_candidate_probes=32,**kw)
                        stack.enter_context(patch.object(adaptive,'best_slide',budgeted))
                    elif variant=='failure_cache':
                        stack.enter_context(activate_cache(cache))
                    started=perf_counter()
                    outcome=run_final_gloss([],pcb,config,GlossConfig(
                        stay_in_corridor=True,budget_seconds=20),net_ids=ids)
                    elapsed=perf_counter()-started
            counters=asdict(search);counters.pop('offsets')
            row=dict(board=board.stem,variant=variant,seconds=elapsed,
                     gain_mm=before-calculate_route_length(pcb.segments),segments=len(pcb.segments),
                     search=counters,cache=cache.stats,stats=outcome.stats,log=log.getvalue().splitlines())
            assert hashlib.sha256(board.read_bytes()).hexdigest()==digest
            data['runs'].append(row)
            args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
            print(board.stem,variant,round(elapsed,3),'s',round(row['gain_mm'],4),'mm',
                  'G5',outcome.stats.get('g5_valid'),'stop',outcome.stats.get('g4_stop_reason'),
                  'probes',search.segment_probes,'candidate_caps',search.candidate_capped,'cache',cache.stats,flush=True)


if __name__=='__main__':main()
