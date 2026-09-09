"""Native, read-only PACK0 comparison of baseline and collinear prototype."""
import argparse
from contextlib import redirect_stdout, nullcontext
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run_one(path, action, variant, net_id=None, text_parser=False):
    if text_parser:
        import gloss
    else:
        from tools import reproduce_corridor_fold as native
    from tools.prototype_collinear_supports import solve_supports
    from dgloss.pipeline import run_centering, run_final_gloss
    from dgloss.config import GlossConfig
    fingerprint=hashlib.sha256(path.read_bytes()).hexdigest()
    started=perf_counter()
    if text_parser:
        pcb=gloss.parse_kicad_pcb(str(path))
    else:
        board=native.pcbnew.LoadBoard(str(path))
        pcb=native.build_pcb_data_from_board(board)
    load_ms=1000*(perf_counter()-started)
    nets=[net_id] if net_id is not None else sorted(n for n in pcb.nets if n)
    with redirect_stdout(io.StringIO()):
        if text_parser:
            args=gloss.build_parser().parse_args([str(path)])
            config=gloss.build_krt_config(args,pcb,nets)
        else:
            config=native.build_krt_config(board,pcb,.1,net_ids=nets)
        started=perf_counter()
        hook=patch('dgloss.support_prototype.solve_supports',solve_supports) if variant=='prototype' else nullcontext()
        with hook:
            if action=='centering':
                outcome=run_centering([],pcb,config,net_ids=nets,proximity_mm=2.54,budget_seconds=20,_emit_log=False)
            else:
                outcome=run_final_gloss([],pcb,config,GlossConfig(stay_in_corridor=True,
                    budget_seconds=20,g4_max_passes=0,enable_multipasses=False),net_ids=nets)
        engine_ms=1000*(perf_counter()-started)
    rows=sorted((s.net_id,s.layer,s.width,min((s.start_x,s.start_y),(s.end_x,s.end_y)),
                 max((s.start_x,s.start_y),(s.end_x,s.end_y))) for s in pcb.segments)
    vias=sorted((v.net_id,v.x,v.y,v.size,v.drill) for v in pcb.vias)
    geometry=hashlib.sha256(repr((rows,vias)).encode()).hexdigest()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==fingerprint
    return dict(board=path.stem,action=action,variant=variant,parser='text' if text_parser else 'native',source_sha256=fingerprint,
                load_ms=load_ms,engine_ms=engine_ms,geometry_sha256=geometry,stats=outcome.stats)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--board',type=Path)
    parser.add_argument('--action',choices=['gloss','centering'])
    parser.add_argument('--variant',choices=['baseline','prototype'])
    parser.add_argument('--net-id',type=int)
    parser.add_argument('--text-parser',action='store_true')
    parser.add_argument('--resume-large',action='store_true')
    args=parser.parse_args()
    if args.board:
        print(json.dumps(run_one(args.board,args.action,args.variant,args.net_id,args.text_parser)))
        return
    manifest=json.loads((ROOT/'docs/PACK0.json').read_text())
    output=ROOT/'.build/collinear-pack0';output.mkdir(parents=True,exist_ok=True)
    rows=json.loads((output/'results.json').read_text()) if args.resume_large else []
    for entry in (manifest['boards'][3:] if args.resume_large else manifest['boards']):
        path=Path(manifest['corpus_root'])/entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
        for action in ('gloss','centering'):
            for variant in ('baseline','prototype'):
                command=[sys.executable,str(Path(__file__).resolve()),'--board',str(path),
                         '--action',action,'--variant',variant]
                if args.text_parser:
                    command.append('--text-parser')
                child=subprocess.run(command,capture_output=True,text=True,timeout=100)
                if child.returncode:
                    raise RuntimeError(child.stdout+'\n'+child.stderr)
                row=json.loads(child.stdout.strip().splitlines()[-1])
                rows.append(row)
                (output/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
                s=row['stats']
                print(entry['name'],action,variant,round(row['engine_ms'],1),'ms',
                      'G5',s.get('g5_valid'),'doors',s.get('doors_centered'),
                      'rollback',s.get('rollback_reason'),flush=True)
    print('REPORT',output/'results.json',flush=True)


if __name__=='__main__':
    main()
