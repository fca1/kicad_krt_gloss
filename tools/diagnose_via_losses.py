"""Causal ablations on the three PACK0 nets with reduced optimization gain."""
import argparse, hashlib, inspect, io, json, sys
from pathlib import Path
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss.context import build_gloss_context
from dgloss.changes import GlossChanges
from dgloss.pipeline import _run_optimization_pass, _route_signature, _grade, _certify_g5_copper
from dgloss.krt_api import via_copper_layers
import tools.progressive_via as proto


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--nets',nargs='+',type=int,default=[112,150,170])
    parser.add_argument('--modes',nargs='+',default=['production','prototype','no_pad_stop','old_score','no_pad_old_score'])
    parser.add_argument('--output',type=Path,default=Path('.build/via_loss_diagnosis.json'))
    args=parser.parse_args()
    pack=json.loads(Path('docs/PACK0.json').read_text()); entry=next(b for b in pack['boards'] if b['name']=='tildagon_base')
    board=Path(pack['corpus_root'])/entry['path']
    source=inspect.getsource(proto.move_mobile_vias)
    needle='math.hypot(position[0]-old_via.x, position[1]-old_via.y), '
    assert source.count(needle)==1
    namespace={}
    exec(compile(source.replace(needle,''),'<old_score>','exec'),proto.__dict__,namespace)
    old_score=namespace['move_mobile_vias']
    nonempty_source=source.replace(needle,'').replace('if candidate and full_chains and not', 'if full_chains and not').replace('if candidate and not context.clearance_adapter.connector_clears', 'if not context.clearance_adapter.connector_clears')
    exec(compile(nonempty_source,'<nonempty>','exec'),proto.__dict__,namespace)
    nonempty=namespace['move_mobile_vias']
    data={'sha256':entry['sha256'],'runs':[]}
    for net in args.nets:
        for mode in args.modes:
            with redirect_stdout(io.StringIO()):
                pcb=gloss.parse_kicad_pcb(str(board)); ids=sorted({s.net_id for s in pcb.segments if s.net_id})
                cfg=gloss.build_krt_config(gloss.build_parser().parse_args([str(board),'--preview']),pcb,ids)
                context=build_gloss_context(pcb,cfg,ids); grade=_grade(pcb,net)
                row={'net':net,'name':pcb.nets[net].name,'mode':mode,'passes':[],'pad_stops':[]}
                original_at_pad=proto._at_pad
                def at_pad(context,via):
                    verdict=original_at_pad(context,via)
                    if verdict:
                        pads=[{'ref':p.component_ref if hasattr(p,'component_ref') else getattr(p,'ref','?'),
                               'xy':(p.global_x,p.global_y),'distance':proto.point_to_pad_distance(via.x,via.y,p)}
                              for p in pcb.pads_by_net.get(net,[])
                              if any(proto._pad_on_layer(p,l) for l in via_copper_layers(via,pcb.board_info.copper_layers))
                              and proto.point_to_pad_distance(via.x,via.y,p)<=via.size/2+1e-6]
                        row['pad_stops'].append({'via':(via.x,via.y),'radius':via.size/2,'pads':pads})
                    return False if 'no_pad' in mode else verdict
                with ExitStack() as stack:
                    if mode!='production':
                        stack.enter_context(patch.object(proto,'_at_pad',at_pad))
                        if 'old_score' in mode: stack.enter_context(patch.object(proto,'move_mobile_vias',old_score))
                        if 'nonempty' in mode: stack.enter_context(patch.object(proto,'move_mobile_vias',nonempty))
                        if 'no_progress' in mode:
                            stack.enter_context(patch.object(proto,'_progressing_vias',lambda ctx,n:[v for v in ctx.pcb_data.vias if v.net_id==n]))
                        stack.enter_context(proto.progressive_via())
                    results=[]; changes=GlossChanges(); sig=_route_signature(pcb,net)
                    for attempt in range(1,11):
                        out=_run_optimization_pass(results,context,GlossConfig(repeat_until_stable=False,budget_seconds=30.),[net],perf_counter()+30,emit_log=False)
                        changes.segments.extend(out['changes'].segments); changes.vias.extend(out['changes'].vias)
                        after=_route_signature(pcb,net)
                        row['passes'].append({'gain':out['before_length']-out['after_length'],
                            'vias': [{'old':(c['old'].x,c['old'].y),'new':(c['new'].x,c['new'].y),'stage':c['stage']} for c in out['changes'].vias],
                            'stages':out['stage_stats'].as_dict()['stages']})
                        if after==sig: break
                        sig=after
                    else: raise AssertionError('No convergence')
                    _certify_g5_copper(context,{net:grade},changes); row['g5']=True
                row['gain']=sum(p['gain'] for p in row['passes'])
            data['runs'].append(row)
            args.output.write_text(json.dumps(data,indent=2),encoding='utf-8')
            print(net,mode,round(row['gain'],6),'G5 valid',flush=True)
    assert hashlib.sha256(board.read_bytes()).hexdigest()==entry['sha256']


if __name__=='__main__': main()
