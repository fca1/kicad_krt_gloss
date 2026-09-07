"""Read-only timing/profile of the modified user board, with explicit settings."""
import argparse,cProfile,hashlib,io,json,pstats,sys
from pathlib import Path
from contextlib import redirect_stdout
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss.pipeline import run_final_gloss,run_centering
from tools.progressive_via import progressive_via


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scope',default='all')
    parser.add_argument('--corridor',action='store_true')
    parser.add_argument('--g4',action='store_true')
    parser.add_argument('--center',action='store_true')
    parser.add_argument('--proximity',type=float,default=1.)
    parser.add_argument('--profile',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    path=Path('C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    tick=perf_counter()
    pcb=gloss.parse_kicad_pcb(str(path)); parse_seconds=perf_counter()-tick
    nets=sorted({s.net_id for s in pcb.segments if s.net_id and (args.scope=='all' or pcb.nets[s.net_id].name==args.scope)})
    cfg=gloss.build_krt_config(gloss.build_parser().parse_args([str(path),'--preview']),pcb,nets)
    log=io.StringIO(); profiler=cProfile.Profile(); tick=perf_counter()
    with redirect_stdout(log),progressive_via():
        if args.profile: profiler.enable()
        try:
            if args.center:
                out=run_centering([],pcb,cfg,net_ids=nets,proximity_mm=args.proximity,budget_seconds=20.)
            else:
                out=run_final_gloss([],pcb,cfg,GlossConfig(stay_in_corridor=args.corridor,repeat_until_stable=args.g4,budget_seconds=20.),net_ids=nets)
        finally:
            if args.profile: profiler.disable()
    seconds=perf_counter()-tick
    data={'sha256':digest,'settings':vars(args),'parse_seconds':parse_seconds,'seconds':seconds,'nets':nets,'stats':out.stats,'log':log.getvalue()}
    args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
    if args.profile:
        profiler.dump_stats(str(args.output.with_suffix('.prof')))
        buffer=io.StringIO();pstats.Stats(profiler,stream=buffer).sort_stats('cumulative').print_stats(35)
        args.output.with_suffix('.profile.txt').write_text(buffer.getvalue())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    print('parse',parse_seconds,'run',seconds,'G5',out.stats.get('g5_valid'))
    print(log.getvalue())


if __name__=='__main__': main()
