"""Measure repeated per-net Gloss with all foreign copper fixed at PACK0 input."""
import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr, nullcontext
import hashlib
import io
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss.changes import GlossChanges
from dgloss.context import build_gloss_context, resolve_gloss_scope
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.search_cache import SearchCache
from dgloss.pipeline import (_run_optimization_pass, _route_signature, _grade,
                            _certify_g5_copper, _restore)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-passes', type=int, default=50)
    parser.add_argument('--net-budget', type=float, default=120.)
    parser.add_argument('--auto-gloss', action='store_true', help='Experimental changed-chain queue; G4 remains disabled')
    parser.add_argument('--output', type=Path, default=Path('.build/net_self_convergence_tildagon.json'))
    args = parser.parse_args()
    pack = json.loads(Path('docs/PACK0.json').read_text(encoding='utf-8'))
    entry = next(b for b in pack['boards'] if b['name']=='tildagon_base')
    board = Path(pack['corpus_root']) / entry['path']
    assert hashlib.sha256(board.read_bytes()).hexdigest()==entry['sha256']
    init_log = io.StringIO()
    started = perf_counter()
    with redirect_stdout(init_log), redirect_stderr(init_log):
        pcb=gloss.parse_kicad_pcb(str(board))
        ids=sorted({s.net_id for s in pcb.segments if s.net_id})
        cli=gloss.build_parser().parse_args([str(board),'--preview'])
        config=gloss.build_krt_config(cli,pcb,ids)
        scope,excluded,reasons=resolve_gloss_scope(pcb,ids)
        context=build_gloss_context(pcb,config,scope,excluded_net_ids=excluded,
                                    exclusion_reasons=reasons)
    original_segments=list(pcb.segments)
    original_vias=list(pcb.vias)
    originals={net:_route_signature(pcb,net) for net in ids}
    data=dict(pack_id='PACK0',board=str(board),sha256=entry['sha256'],
        setup_seconds=perf_counter()-started,max_passes=args.max_passes,
        net_budget_seconds=args.net_budget,
        protocol='One independent convergence sequence per eligible net, sorted id; each starts from original board; foreign nets remain fixed; full production chain per call, corridor=False, no G4, no Centering, no marginal cutoff; unchanged geometric signature confirms fixed point; last no-change call included in calls_to_confirm; setup/reset/certification separately timed',
        excluded=list(excluded),runs=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    selected=GlossConfig(repeat_until_stable=False,budget_seconds=args.net_budget)
    data['variant']='auto_gloss' if args.auto_gloss else 'production'
    data['g4_enabled']=False
    if args.auto_gloss:
        from tools.auto_gloss import auto_gloss
        data['protocol']=data['protocol'].replace('full production chain per call', 'production stages with auto gloss changed-chain queue per call')
    for index,net in enumerate(scope):
        row=dict(net_id=net,name=pcb.nets[net].name,passes=[],status='pass_limit',
                 initial_segments=sum(s.net_id==net for s in original_segments),
                 initial_vias=sum(v.net_id==net for v in original_vias))
        log=io.StringIO()
        results=[]
        changes=GlossChanges()
        signature=originals[net]
        seen={signature}
        begin=perf_counter()
        deadline=begin+args.net_budget
        try:
            with redirect_stdout(log),redirect_stderr(log):
                before_grade=_grade(pcb,net)
                for attempt in range(1,args.max_passes+1):
                    if perf_counter()>=deadline:
                        row['status']='budget'
                        break
                    tick=perf_counter()
                    with auto_gloss() if args.auto_gloss else nullcontext() as auto_stats:
                        outcome=_run_optimization_pass(results,context,selected,[net],deadline,emit_log=False)
                    elapsed=perf_counter()-tick
                    live_segments={id(s) for s in pcb.segments}
                    assert all(id(s) in live_segments for result in results
                               for s in result.get('new_segments', [])), 'stale output segment'
                    changes.segments.extend(outcome['changes'].segments)
                    changes.vias.extend(outcome['changes'].vias)
                    after=_route_signature(pcb,net)
                    stages=outcome['stage_stats'].as_dict()['stages']
                    completed=perf_counter()<deadline
                    row['passes'].append(dict(index=attempt,seconds=elapsed,
                        gain_mm=outcome['before_length']-outcome['after_length'],
                        geometry_changed=after!=signature,completed=completed,
                        stages=stages,auto_gloss=dict(auto_stats) if auto_stats is not None else None))
                    if not completed:
                        row['status']='budget'
                        break
                    if after==signature:
                        row['status']='fixed_point'
                        break
                    if after in seen:
                        row['status']='cycle'
                        break
                    seen.add(after)
                    signature=after
                tick=perf_counter()
                row['g5']=_certify_g5_copper(context,{net:before_grade},changes)
                row['g5_seconds']=perf_counter()-tick
                row['g5_valid']=True
        except Exception as exc:
            row['status']='error'
            row['error']=str(exc)
            row['g5_valid']=False
        row['sequence_seconds']=perf_counter()-begin
        row['gain_mm']=sum(p['gain_mm'] for p in row['passes'])
        row['gain_after_first_mm']=sum(p['gain_mm'] for p in row['passes'][1:])
        row['productive_calls']=sum(p['geometry_changed'] for p in row['passes'])
        row['calls_to_confirm']=len(row['passes']) if row['status']=='fixed_point' else None
        row['log']=log.getvalue().splitlines()
        # Validate foreign geometry before restoring the original single net.
        assert all(_route_signature(pcb,other)==originals[other] for other in ids if other!=net)
        tick=perf_counter()
        changed_segments=[s for s in pcb.segments if s.net_id==net]
        changed_vias=[v for v in pcb.vias if v.net_id==net]
        _restore(results,0,[],pcb,list(original_segments),list(original_vias))
        context.replace_editable_segments(changed_segments,
            [s for s in original_segments if s.net_id==net],changed_vias,
            [v for v in original_vias if v.net_id==net])
        context.refresh_net_obstacles(net)
        # Discard search certificates between independent experiments.
        context.search_cache=SearchCache(pcb,config)
        context.clearance_adapter=KrtClearanceAdapter(pcb,config)
        row['reset_seconds']=perf_counter()-tick
        assert _route_signature(pcb,net)==originals[net]
        data['runs'].append(row)
        args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
        print(f"{index+1}/{len(scope)} net {net} {row['name']}: {row['status']}, "
              f"calls={len(row['passes'])}, extra_gain={row['gain_after_first_mm']:.4f} mm, "
              f"{row['sequence_seconds']:.3f}s",flush=True)
    assert hashlib.sha256(board.read_bytes()).hexdigest()==entry['sha256']
    data['source_unchanged']=True
    data['statuses']=dict(Counter(r['status'] for r in data['runs']))
    data['calls_histogram']=dict(Counter(r['calls_to_confirm'] for r in data['runs'] if r['calls_to_confirm'] is not None))
    args.output.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
    print(json.dumps(dict(statuses=data['statuses'],calls=data['calls_histogram'])))


if __name__=='__main__':
    main()
