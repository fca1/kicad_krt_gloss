"""Diagnostic replay of one PACK0 net (59 by default), not a timing benchmark."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import argparse
import hashlib
import inspect
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss.context import build_gloss_context
from dgloss.changes import GlossChanges
import dgloss.pipeline as pipeline
import dgloss.via_mobile as via_module

TARGET_NET=59

def snapshot(pcb):
    return dict(segments=[(s.layer,s.width,s.start_x,s.start_y,s.end_x,s.end_y)
        for s in pcb.segments if s.net_id==TARGET_NET],
        vias=[(v.x,v.y,v.size,v.drill) for v in pcb.vias if v.net_id==TARGET_NET])


def main():
    global TARGET_NET
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--net',type=int,default=59)
    parser.add_argument('--output',type=Path,default=Path('.build/trace_btn4_passes.json'))
    args=parser.parse_args()
    TARGET_NET=args.net
    pack=json.loads(Path('docs/PACK0.json').read_text())
    entry=next(b for b in pack['boards'] if b['name']=='tildagon_base')
    board=Path(pack['corpus_root'])/entry['path']
    assert hashlib.sha256(board.read_bytes()).hexdigest()==entry['sha256']
    log=io.StringIO();data=dict(net_id=TARGET_NET,sha256=entry['sha256'],events=[],stages=[])
    pass_no=[0]
    function=via_module.move_mobile_vias
    lines,start_line=inspect.getsourcelines(function)
    reasons={}
    # Record executed rejection/selection lines using the checked-in function's
    # source, avoiding hard-coded offsets across future edits.
    for offset,line in enumerate(lines):
        if line.strip()=='continue' and offset:
            previous=' '.join(l.strip() for l in lines[max(0,offset-3):offset])
            reasons[start_line+offset]=previous
        if line.strip()=='best = score, moved_via, candidate':
            reasons[start_line+offset]='eligible_best'
    def trace(frame,event,arg):
        if frame.f_code is not function.__code__:
            return None
        if event=='line' and frame.f_lineno in reasons:
            local=frame.f_locals
            via=local.get('old_via')
            if via is not None and via.net_id==TARGET_NET and 'position' in local:
                data['events'].append(dict(pass_no=pass_no[0],stage=local['stage'],
                    via=(via.x,via.y),position=local['position'],anchors=local.get('anchors'),
                    old_length=local.get('old_length'),new_length=local.get('new_length'),
                    reason=reasons[frame.f_lineno],line=frame.f_lineno))
        return trace
    with redirect_stdout(log),redirect_stderr(log):
        pcb=gloss.parse_kicad_pcb(str(board))
        ids=sorted({s.net_id for s in pcb.segments if s.net_id})
        cli=gloss.build_parser().parse_args([str(board),'--preview'])
        config=gloss.build_krt_config(cli,pcb,ids)
        context=build_gloss_context(pcb,config,ids)
        data['net_name']=pcb.nets[TARGET_NET].name
        initial=pipeline._route_signature(pcb,TARGET_NET)
        grade=pipeline._grade(pcb,TARGET_NET)
        data['initial']=snapshot(pcb)
        changes=GlossChanges();results=[]
        with ExitStack() as stack:
            for name in ('shorten_routes','move_mobile_vias','optimize_pad_terminals',
                         'slide_t_nodes','refine_mobile_vias','_merge_collinear_in_scope'):
                original=getattr(pipeline,name)
                def wrapped(*args,_original=original,_name=name,**kwargs):
                    before=snapshot(pcb)
                    outcome=_original(*args,**kwargs)
                    after=snapshot(pcb)
                    data['stages'].append(dict(pass_no=pass_no[0],function=_name,
                        stage=kwargs.get('stage'),objective=kwargs.get('objective'),
                        before=before,after=after,changed=before!=after))
                    return outcome
                stack.enter_context(patch.object(pipeline,name,wrapped))
            old_trace=sys.gettrace()
            sys.settrace(trace)
            try:
                for number in range(1,7):
                    pass_no[0]=number
                    outcome=pipeline._run_optimization_pass(results,context,
                        GlossConfig(repeat_until_stable=False),[TARGET_NET],float('inf'),emit_log=False)
                    changes.segments.extend(outcome['changes'].segments)
                    changes.vias.extend(outcome['changes'].vias)
                    signature=pipeline._route_signature(pcb,TARGET_NET)
                    if signature==initial:
                        break
                    initial=signature
            finally:
                sys.settrace(old_trace)
        data['g5']=pipeline._certify_g5_copper(context,{TARGET_NET:grade},changes)
    assert hashlib.sha256(board.read_bytes()).hexdigest()==entry['sha256']
    data['source_unchanged']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2),encoding='utf-8')
    print('passes',pass_no[0],'events',len(data['events']),'G5',data['g5'])


if __name__=='__main__':main()
