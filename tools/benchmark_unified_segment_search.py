"""Current versus common local search in both corridor modes; no repetitions."""
import argparse
from contextlib import nullcontext,redirect_stdout,redirect_stderr
from dataclasses import asdict
import hashlib,io,json
from pathlib import Path
import sys
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig,run_final_gloss
from dgloss.krt_api import calculate_route_length
from tools.adaptive_segment_slide import SearchStats
from tools.unified_segment_search import activate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boards',nargs='+',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    data=dict(protocol='one run per board/variant/corridor, no warm-up; budget20s; no Centering',runs=[],inputs={})
    modes=[('current',False),('unified',False),('current',True),('unified',True)]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for i,board in enumerate(args.boards):
        digest=hashlib.sha256(board.read_bytes()).hexdigest();data['inputs'][str(board)]=digest
        for variant,corridor in modes[i:]+modes[:i]:
            log=io.StringIO();search=SearchStats()
            with redirect_stdout(log),redirect_stderr(log):
                pcb=gloss.parse_kicad_pcb(str(board));ids=sorted({s.net_id for s in pcb.segments if s.net_id})
                options=gloss.build_parser().parse_args([str(board),'--preview'])
                config=gloss.build_krt_config(options,pcb,ids)
                before=calculate_route_length(pcb.segments)
                with activate(search) if variant=='unified' else nullcontext():
                    started=perf_counter()
                    outcome=run_final_gloss([],pcb,config,GlossConfig(
                        stay_in_corridor=corridor,budget_seconds=20),net_ids=ids)
                    elapsed=perf_counter()-started
            counters=asdict(search);counters.pop('offsets')
            row=dict(board=board.stem,variant=variant,corridor=corridor,seconds=elapsed,
                     gain_mm=before-calculate_route_length(pcb.segments),segments=len(pcb.segments),
                     search=counters,stats=outcome.stats,log=log.getvalue().splitlines())
            assert hashlib.sha256(board.read_bytes()).hexdigest()==digest
            data['runs'].append(row)
            args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
            print(board.stem,variant,'corridor',corridor,round(elapsed,3),'s',round(row['gain_mm'],4),'mm',
                  'G5',outcome.stats.get('g5_valid'),'stop',outcome.stats.get('g4_stop_reason'),flush=True)


if __name__=='__main__':main()
