"""Exercise the opt-in EB dialog on a detached board; never SaveBoard."""
import argparse
import hashlib
from pathlib import Path
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
package=types.ModuleType('_eb_probe')
package.__path__=[str(ROOT/'kicad_krt_gloss')]
sys.modules[package.__name__]=package
from _eb_probe.runtime import configure_krt_runtime
configure_krt_runtime()
import pcbnew
import wx
from _eb_probe import action_plugin as action
from _eb_probe.branch_selection_prototype import activate, track_index
from dgloss.branches import elementary_branch_segment_ids


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('board',type=Path)
    parser.add_argument('--action',choices=['gloss','centering'],default='centering')
    args=parser.parse_args()
    fingerprint=hashlib.sha256(args.board.read_bytes()).hexdigest()
    board=pcbnew.LoadBoard(str(args.board.resolve()))
    action.KICAD.refresh=lambda: None  # Detached board, no editor to repaint.
    app=wx.App(False)
    def error(message,*a,**k):
        raise AssertionError(message)
    wx.MessageBox=error
    restore=activate(action,board_provider=lambda:board)
    plugin=action.KiCadKrtGlossPlugin()
    data=action.KICAD.build_pcb_data(board)
    rows=plugin._modifiable_net_rows(board,data)
    net=next(n for name,n in rows if name=='/A')
    for track in board.GetTracks():track.ClearSelected()
    dialog=action.GlossSettingsDialog(None,dict(action.DEFAULTS,centering_proximity_mm=2.54),0,
        pcb_data=data,centering_nets=rows,preselected_centering_nets=['/A'])
    assert dialog.grid_step.GetFont().GetPointSize()==dialog.centering_proximity_mm.GetFont().GetPointSize()
    assert dialog.budget_seconds.GetFont().GetPointSize()==dialog.centering_proximity_mm.GetFont().GetPointSize()
    def toggle_eb(enabled):
        control=dialog.controls['selection_uses_elementary_branches']
        control.SetValue(enabled)
        event=wx.CommandEvent(wx.EVT_CHECKBOX.typeId,control.GetId())
        event.SetEventObject(control)
        control.GetEventHandler().ProcessEvent(event)
        actual=bytes(dialog._scope_illustration.GetBitmap().ConvertToImage().GetData())
        expected=bytes(dialog._scope_bitmaps[enabled].ConvertToImage().GetData())
        assert actual==expected
        return actual
    net_pixels=toggle_eb(False)
    branch_pixels=toggle_eb(True)
    assert net_pixels!=branch_pixels
    index=track_index(board,data,pcbnew)
    groups={}
    reverse={id(s):uid for uid,s in index.items()}
    for uid,s in index.items():
        if s.net_id==net:
            ids,_=elementary_branch_segment_ids(data,[s])
            groups[frozenset(reverse[i] for i in ids)]=uid
    branches=sorted(groups,key=len,reverse=True)
    assert len(branches)>1
    def select(uids):
        for track in board.GetTracks():
            if track.m_Uuid.AsString() in uids:track.SetSelected()
            else:track.ClearSelected()
    select([groups[branches[0]]])
    dialog._on_import_centering(False)
    assert len(dialog._branch_memory.by_net['/A'])==1
    select([groups[branches[1]]])
    dialog._on_import_centering(True)
    dialog._on_import_centering(True)
    assert len(dialog._branch_memory.by_net['/A'])==2
    select([])
    net_list=dialog.centering_net_panel.net_list
    for i in net_list.GetSelections():net_list.Deselect(i)
    net_list.SetSelection(net_list.FindString('/A'))
    dialog._on_centering_net_row_selected(types.SimpleNamespace(Skip=lambda:None))
    visible={t.m_Uuid.AsString() for t in board.GetTracks() if t.IsBrightened()}
    expected=set().union(*(b.tracks|b.vias for b in dialog._branch_memory.by_net['/A']))
    assert visible==expected
    assert not any(t.IsSelected() for t in board.GetTracks())
    ready,chosen=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert len(ready[1])==len(branches[0]|branches[1])
    toggle_eb(False)
    whole,_=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert len(whole[1])==sum(s.net_id==net for s in whole[0].segments)
    toggle_eb(True)
    assert len(dialog._branch_memory.by_net['/A'])==2
    dialog._on_clear_centering_selection(None)
    assert not dialog._branch_memory.by_net and not dialog.centering_net_panel.get_selected_nets()
    dialog.centering_net_panel.set_selected_nets(['/A'])
    whole,_=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert len(whole[1])==sum(s.net_id==net for s in whole[0].segments)
    select([groups[branches[0]]])
    dialog._on_import_centering(False)
    select([groups[branches[1]]])  # Action must ignore this later live selection.
    ready,chosen=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert len(ready[1])==len(branches[0])
    fixed={t.m_Uuid.AsString():(t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth())
           for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.m_Uuid.AsString() not in branches[0]}
    before_ids={t.m_Uuid.AsString() for t in board.GetTracks()}
    if args.action=='centering':
        result=plugin._run_centering(board,dialog,dialog.values(),['/A'],prepared=ready,append_log=dialog.append_log)
        assert result and result['doors_centered']==3
    else:
        result=plugin._run_gloss(board,dialog,dialog.values(),chosen,prepared=ready,append_log=dialog.append_log,show_progress=False)
        assert result
    current={t.m_Uuid.AsString():(t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth())
             for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'}
    assert all(current.get(uid)==geometry for uid,geometry in fixed.items())
    # Actual full-line overlay geometries must use the display-only 0.1 mm.
    full=[g for g in board.GetDrawings() if board.GetLayerName(g.GetLayer())=='TrackGloss Changes'
          and g.GetWidth()==pcbnew.FromMM(.1)]
    for track in board.GetTracks():
        if track.GetClass()=='PCB_TRACK' and track.m_Uuid.AsString() not in before_ids:
            assert any((g.GetStart()==track.GetStart() and g.GetEnd()==track.GetEnd()) or
                       (g.GetEnd()==track.GetStart() and g.GetStart()==track.GetEnd()) for g in full)
    stale,_=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert stale is None  # Replaced UUIDs must not widen the next operation.
    dialog._branch_highlighter(())
    dialog.Destroy();app.ProcessPendingEvents();restore()
    assert hashlib.sha256(args.board.read_bytes()).hexdigest()==fingerprint
    print('PASS',args.action,'remembered branches, Add/Replace/Clear, highlight IDs, whole-net fallback, fonts, outside copper preserved; source unchanged')


if __name__=='__main__':main()
