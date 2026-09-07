"""Profile the delivered ZIP under KiCad Python on a detached native board."""
import argparse,cProfile,hashlib,inspect,io,json,pstats,sys,types
from pathlib import Path
from time import perf_counter
from contextlib import redirect_stdout
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--corridor',action='store_true')
parser.add_argument('--profile',action='store_true')
parser.add_argument('--layer-width',action='store_true',help='Diagnostic only: supply F.Cu to the native via GetWidth call')
parser.add_argument('--scope',default='all')
args=parser.parse_args()
package=root/'.build/progressive_zip_check/plugins'
sys.path.insert(0,str(package))
import runtime
runtime.configure_krt_runtime()
import pcbnew
from dgloss.krt_api import build_pcb_data_from_board
from dgloss import GlossConfig
from dgloss.pipeline import run_final_gloss
stub=types.ModuleType('native_probe_plugin');stub.__path__=[str(package)]
sys.modules['native_probe_plugin']=stub
from native_probe_plugin.board_adapter import build_krt_config,apply_gloss
if args.layer_width:
    import native_probe_plugin.board_adapter as adapter
    source=inspect.getsource(adapter._native_via_key)
    assert source.count('via.GetWidth()')==1
    exec(compile(source.replace('via.GetWidth()','via.GetWidth(pcbnew.F_Cu)'),'<explicit-via-layer>','exec'),adapter.__dict__)
path=Path('C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb')
digest=hashlib.sha256(path.read_bytes()).hexdigest()
times={}; profiler=cProfile.Profile(); log=io.StringIO()
if args.profile: profiler.enable()
with redirect_stdout(log):
    tick=perf_counter();board=pcbnew.LoadBoard(str(path));times['native_load']=perf_counter()-tick
    tick=perf_counter();pcb=build_pcb_data_from_board(board);times['native_export']=perf_counter()-tick
    nets=sorted({s.net_id for s in pcb.segments if s.net_id and (args.scope=='all' or pcb.nets[s.net_id].name==args.scope)})
    tick=perf_counter();cfg=build_krt_config(board,pcb,.1,net_ids=nets);times['config']=perf_counter()-tick
    tick=perf_counter();results=[]
    outcome=run_final_gloss(results,pcb,cfg,GlossConfig(stay_in_corridor=args.corridor,budget_seconds=20.),net_ids=nets)
    times['engine']=perf_counter()-tick
    if outcome.stats.get('g5_valid'):
        tick=perf_counter();apply_gloss(board,results,outcome);times['native_apply']=perf_counter()-tick
if args.profile: profiler.disable()
assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
data={'sha256':digest,'times':times,'stats':outcome.stats,'log':log.getvalue(),'source_unchanged':True,'package':str(package),'settings':vars(args)}
dest=root/'.build'/('native_modified_'+('corridor' if args.corridor else 'free')+('_layer' if args.layer_width else '')+('_profile' if args.profile else '')+'.json')
dest.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
if args.profile:
    profiler.dump_stats(str(dest.with_suffix('.prof')))
    buffer=io.StringIO();pstats.Stats(profiler,stream=buffer).sort_stats('cumulative').print_stats(40)
    dest.with_suffix('.profile.txt').write_text(buffer.getvalue())
print(json.dumps(times));print(log.getvalue())
