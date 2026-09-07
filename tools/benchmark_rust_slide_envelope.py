"""Observe Rust swept envelopes without using their answers for acceptance."""
import argparse
from contextlib import redirect_stdout,redirect_stderr
import hashlib,io,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig,run_final_gloss
from tools.adaptive_segment_slide import SearchStats,activate
from tools.rust_slide_envelope import Observer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    digest=hashlib.sha256(args.board.read_bytes()).hexdigest()
    log=io.StringIO();observer=Observer();search=SearchStats()
    with redirect_stdout(log),redirect_stderr(log):
        pcb=gloss.parse_kicad_pcb(str(args.board))
        ids=sorted({s.net_id for s in pcb.segments if s.net_id})
        options=gloss.build_parser().parse_args([str(args.board),'--preview'])
        config=gloss.build_krt_config(options,pcb,ids)
        with observer.activate(),activate(search):
            outcome=run_final_gloss([],pcb,config,GlossConfig(
                stay_in_corridor=True,budget_seconds=120),net_ids=ids)
    assert hashlib.sha256(args.board.read_bytes()).hexdigest()==digest
    data=dict(board=str(args.board),sha256=digest,source_unchanged=True,
        protocol='one instrumented run; Rust answers never change acceptance; 120s budget for instrumentation',
        grid_step=config.grid_step,clearance=config.clearance,track_width=config.track_width,
        reserve_widths={layer:config.route_reserve_width(layer) for layer in config.layers},
        queries=observer.queries,offgrid=observer.offgrid,exact_seconds=observer.exact_seconds,
        map_seconds=observer.map_seconds,variants=dict(observer.totals),
        disagreements=observer.disagreements,stats=outcome.stats)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in ('stats','disagreements')},indent=2))
    print('gain',outcome.stats.get('saved_mm'),'G5',outcome.stats.get('g5_valid'),'stop',outcome.stats.get('g4_stop_reason'))


if __name__=='__main__':main()
