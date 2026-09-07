"""Compare production/prototype on the user's test_centering2 /B case."""
import io
import json
import hashlib
import sys
from pathlib import Path
from contextlib import nullcontext, redirect_stdout
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss.changes import GlossChanges
from dgloss.context import build_gloss_context
from dgloss.pipeline import _run_optimization_pass, _route_signature, _grade, _certify_g5_copper
from tools.progressive_via import progressive_via


def main():
    path=Path('C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    data={'board':str(path),'sha256':digest,'g4':False,'runs':[]}
    for corridor in (False,True):
        for prototype in (False,True):
            with redirect_stdout(io.StringIO()):
                pcb=gloss.parse_kicad_pcb(str(path))
                net=next(n for n,v in pcb.nets.items() if v.name=='/B')
                cfg=gloss.build_krt_config(gloss.build_parser().parse_args([str(path),'--preview']),pcb,[net])
                context=build_gloss_context(pcb,cfg,[net]); grade=_grade(pcb,net)
                originals={n:_route_signature(pcb,n) for n in pcb.nets if n!=net}
                selected=GlossConfig(stay_in_corridor=corridor,repeat_until_stable=False,budget_seconds=30.)
                changes=GlossChanges(); results=[]; before=_route_signature(pcb,net)
                row={'corridor':corridor,'prototype':prototype,'net':net,'passes':[],'status':'cap'}
                deadline=perf_counter()+30
                for i in range(10):
                    tick=perf_counter()
                    with progressive_via() if prototype else nullcontext():
                        out=_run_optimization_pass(results,context,selected,[net],deadline,emit_log=False)
                    elapsed=perf_counter()-tick
                    changes.segments.extend(out['changes'].segments); changes.vias.extend(out['changes'].vias)
                    after=_route_signature(pcb,net)
                    row['passes'].append({'index':i+1,'seconds':elapsed,'gain_mm':out['before_length']-out['after_length'],
                        'length_mm':out['after_length'],'vias':[(v.x,v.y) for v in pcb.vias if v.net_id==net],
                        'via_events':[{'old':(c['old'].x,c['old'].y),'new':(c['new'].x,c['new'].y)} for c in out['changes'].vias],
                        'stages':out['stage_stats'].as_dict()['stages']})
                    if perf_counter()>=deadline: row['status']='budget'; break
                    if after==before: row['status']='fixed_point'; break
                    before=after
                _certify_g5_copper(context,{net:grade},changes); row['g5_valid']=True
                assert all(_route_signature(pcb,n)==sig for n,sig in originals.items())
            data['runs'].append(row)
            print(json.dumps(row))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    data['source_unchanged']=True
    Path('.build/progressive_via_B.json').write_text(json.dumps(data,indent=2),encoding='utf-8')


if __name__=='__main__': main()
