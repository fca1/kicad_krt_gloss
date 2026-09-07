"""One run per variant per known board, without warm-up or repetitions."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss.pipeline import run_final_gloss
from net_queries import calculate_route_length
from tools.reduction_motion import MotionCertificate, activate


def run(board, mode, budget):
    log = io.StringIO()
    motion = MotionCertificate() if mode != 'baseline' else None
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        start = perf_counter()
        pcb = gloss.parse_kicad_pcb(str(board))
        ids = sorted({s.net_id for s in pcb.segments if s.net_id})
        options = gloss.build_parser().parse_args([str(board),'--preview'])
        config = gloss.build_krt_config(options, pcb, ids)
        before = dict(segments=len(pcb.segments), vias=len(pcb.vias), nets=len(ids),
                      length_mm=calculate_route_length(pcb.segments))
        load = perf_counter()-start
        with activate(motion, early_pad=mode=='motion_pad'):
            start = perf_counter()
            outcome = run_final_gloss([], pcb, config,
                GlossConfig(stay_in_corridor=True,budget_seconds=budget),net_ids=ids)
            elapsed = perf_counter()-start
        after = dict(segments=len(pcb.segments), vias=len(pcb.vias),
                     length_mm=calculate_route_length(pcb.segments))
    return dict(board=str(board),mode=mode,load_seconds=load,seconds=elapsed,
                before=before,after=after,gain_mm=before['length_mm']-after['length_mm'],
                motion=motion.stats if motion else None,grid_mm=config.grid_step,
                stats=outcome.stats,log=log.getvalue().splitlines())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('boards',nargs='+',type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--budget',type=float,default=20.)
    args=p.parse_args()
    data=dict(protocol='one run per variant, no warm-up, corridor=True, no Centering',
              budget=args.budget,inputs={},runs=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    modes=['baseline','motion','motion_pad']
    for i,board in enumerate(args.boards):
        digest=hashlib.sha256(board.read_bytes()).hexdigest()
        data['inputs'][str(board)]=dict(sha256=digest)
        for mode in modes[i%3:]+modes[:i%3]:
            row=run(board,mode,args.budget)
            args_unchanged=hashlib.sha256(board.read_bytes()).hexdigest()==digest
            row['input_unchanged']=args_unchanged
            data['runs'].append(row)
            args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
            print(board.stem,mode,round(row['seconds'],3),'s',round(row['gain_mm'],4),
                  'mm G5',row['stats'].get('g5_valid',False),
                  row['stats'].get('g4_stop_reason'),row['motion'],flush=True)
            assert args_unchanged


if __name__=='__main__':
    main()
