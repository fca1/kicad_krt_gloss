"""Read-only comparisons, G4 disabled, isolated modes and exact output hashes."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gloss
from dgloss import GlossConfig, run_final_gloss
from dgloss.krt_clearance import KrtClearanceAdapter
from dgloss.pipeline import _route_signature
from tools.prototype_gloss_perf import activate, MODES
from tools.benchmark_architecture import acute_chain_joints


def exact_geometry(pcb):
    return (sorted((s.net_id, s.layer, s.width, s.start_x, s.start_y, s.end_x, s.end_y,
                    bool(s.graphic), bool(s.locked)) for s in pcb.segments),
            sorted((v.net_id, v.x, v.y, v.size, v.drill, tuple(v.layers), bool(v.locked)) for v in pcb.vias))


def run(board, modes, corridor, budget):
    log = io.StringIO()
    with redirect_stdout(log):
        start = perf_counter()
        pcb = gloss.parse_kicad_pcb(str(board))
        ids = sorted({s.net_id for s in pcb.segments if s.net_id})
        cfg = gloss.build_krt_config(gloss.build_parser().parse_args([str(board),'--preview']), pcb, ids)
        load = perf_counter()-start
        original_ids = {id(s) for s in pcb.segments}
        before = {net: acute_chain_joints(_route_signature(pcb,net), pcb.pads_by_net.get(net,[])) for net in ids}
        # Installation and audits are outside the timed engine; no PCB is saved.
        with activate(modes):
            start = perf_counter()
            out = run_final_gloss([], pcb, cfg, GlossConfig(budget_seconds=budget,
                repeat_until_stable=False, enable_multipasses=False, stay_in_corridor=corridor), net_ids=ids)
            elapsed = perf_counter()-start
    audit = KrtClearanceAdapter(pcb,cfg)  # original implementation, hooks removed
    new = [s for s in pcb.segments if id(s) not in original_ids]
    preserved = {id(e['new']) for e in out.changes.get('segments',[]) if 'new' in e and e.get('geometry_preserving')}
    violations = sum(not audit.segment_clears(s) for s in new if id(s) not in preserved)
    non_octolinear = sum(min(abs(s.end_x-s.start_x), abs(s.end_y-s.start_y),
        abs(abs(s.end_x-s.start_x)-abs(s.end_y-s.start_y))) > 1e-7 for s in new)
    acute = sum(len(acute_chain_joints(_route_signature(pcb,n),pcb.pads_by_net.get(n,[]))-before[n]) for n in ids)
    return dict(seconds=elapsed, load_seconds=load, modes=list(modes), corridor=corridor,
        budget=budget, grid=cfg.grid_step, g4=False, nets=out.stats.get('nets_processed'),
        saved_mm=out.stats.get('saved_mm'), g5=out.stats.get('g5_valid'),
        expired=out.stats.get('gloss',{}).get('budget_expired'),
        geometry=hashlib.sha256(json.dumps(exact_geometry(pcb)).encode()).hexdigest(),
        non_octolinear=non_octolinear, new_acute=acute, clearance_violations=violations,
        stages=out.stats.get('gloss',{}).get('stages',{}),
        log=log.getvalue().splitlines())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--boards',nargs='+')
    p.add_argument('--variants',nargs='+',default=['combined'])
    p.add_argument('--corridors',nargs='+',type=int,default=[0,1],choices=[0,1])
    p.add_argument('--budget',type=float,default=120.)
    p.add_argument('--combined-modes',nargs='+',choices=MODES,default=list(MODES))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify-integrated',type=Path,
                   help='Compare production (no hooks) to a recorded prototype PACK0 result')
    args=p.parse_args()
    expected = json.loads(args.verify_integrated.read_text()) if args.verify_integrated else None
    if expected is None and hasattr(KrtClearanceAdapter, '_via_clears_exact'):
        p.error('Prototype already integrated: use --verify-integrated or run comparisons from the baseline checkout')
    pack=json.loads((ROOT/'docs/PACK0.json').read_text())
    rows=[]; failed=False
    for entry in pack['boards']:
        if args.boards and entry['name'] not in args.boards:continue
        board=Path(pack['corpus_root'])/entry['path']
        assert hashlib.sha256(board.read_bytes()).hexdigest()==entry['sha256']
        for corridor in args.corridors:
            variants=['integrated'] if expected is not None else ['baseline']+args.variants
            # Alternate order on the second configuration, without warming up.
            if corridor:variants.reverse()
            group=[]
            for variant in variants:
                modes=() if variant in ('baseline','integrated') else args.combined_modes if variant=='combined' else [variant]
                row=run(board,modes,bool(corridor),args.budget)
                row.update(board=entry['name'],variant=variant,sha256=entry['sha256'])
                group.append(row); rows.append(row)
                assert hashlib.sha256(board.read_bytes()).hexdigest()==entry['sha256']
                failed |= not row['g5'] or bool(row['expired']) or bool(row['non_octolinear'] or row['new_acute'] or row['clearance_violations'])
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(rows,indent=2),encoding='utf-8')
                print(json.dumps({k:v for k,v in row.items() if k not in ('stages','log')}),flush=True)
            base=(next(r for r in expected if r['board']==entry['name'] and
                       r['corridor']==bool(corridor) and r['variant']=='combined')
                  if expected is not None else next(r for r in group if r['variant']=='baseline'))
            for row in group:
                row['identical_geometry']=row['geometry']==base['geometry']
                if expected is None:
                    row['gain_percent']=100*(base['seconds']-row['seconds'])/base['seconds']
                failed |= not row['identical_geometry']
            args.output.write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return int(failed)


if __name__=='__main__':raise SystemExit(main())
