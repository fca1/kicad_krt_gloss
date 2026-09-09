"""Exercise the opt-in EB dialog on a detached board; never SaveBoard."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
package=types.ModuleType('_eb_probe')
package.__path__=[os.environ.get('KRG_TEST_PLUGIN_ROOT',str(ROOT/'kicad_krt_gloss'))]
sys.modules[package.__name__]=package
from _eb_probe.runtime import configure_krt_runtime
configure_krt_runtime()
import pcbnew
import wx
import wx.dataview as dv
from _eb_probe import action_plugin as action
from _eb_probe.branch_selection_prototype import activate, track_index
from dgloss.branches import elementary_branch_segment_ids


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('board',type=Path)
    parser.add_argument('--action',choices=['gloss','centering'],default='centering')
    parser.add_argument('--scope',choices=['single','multiple','whole','eb-off','complete'],default='single')
    parser.add_argument('--show-layout',action='store_true')
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
        pcb_data=data,centering_nets=rows,preselected_centering_nets=[])
    assert dialog.centering_net_panel.get_selected_nets()==[]
    assert not dialog.gloss_button.IsEnabled() and not dialog.centering_button.IsEnabled()
    reveal_calls=[]
    scope_list=dialog.centering_net_panel.net_list
    assert scope_list.GetWindowStyleFlag() & dv.DV_VERT_RULES
    reveal=scope_list.reveal_first_changed
    def record_reveal(names):
        row=reveal(names)
        reveal_calls.append((set(names),row))
        return row
    scope_list.reveal_first_changed=record_reveal
    if args.show_layout:
        dialog.Show()
        wx.Yield()
    assert dialog.grid_step.GetFont().GetPointSize()==dialog.centering_proximity_mm.GetFont().GetPointSize()
    assert dialog.budget_seconds.GetFont().GetPointSize()==dialog.centering_proximity_mm.GetFont().GetPointSize()
    for child in dialog._general_panel.GetChildren():
        if isinstance(child,(wx.StaticText,wx.StaticBox)) and child.GetLabel() in (
                'Calculation Settings / Execution Limit','KRT grid step (mm):','Time budget:','s'):
            assert child.GetFont().GetPointSize()==dialog._general_panel.GetFont().GetPointSize()
    dialog.notebook.GetPage(0).Layout()
    assert dialog.grid_step.GetRect().GetRight()==dialog.budget_seconds.GetRect().GetRight()
    opening=dialog.GetSize()
    minimum=dialog.GetMinSize()
    assert minimum.width < opening.width
    dialog.SetSize(minimum)
    dialog.Layout()
    dialog._on_general_size()
    if args.show_layout:
        wx.Yield()
        item=scope_list.RowToItem(0)
        scope_list.EnsureVisible(item)
        wx.Yield()
        eb_rect=scope_list.GetItemRect(item,scope_list.GetColumn(2))
        net_rect=scope_list.GetItemRect(item,scope_list.GetColumn(1))
        print('VISIBLE COLUMNS:',net_rect,eb_rect)
        assert eb_rect.width <= scope_list.FromDIP(60)
        assert net_rect.width > eb_rect.width
        assert scope_list.FromDIP(120) <= net_rect.width <= scope_list.FromDIP(180)
        # The list must fill its container, not leave a blank region on its right.
        assert scope_list.GetSize().width == dialog.centering_net_panel._list_container_sizer.GetSize().width
    assert dialog.GetSize().width==minimum.width
    assert dialog._general_columns.GetOrientation()==wx.HORIZONTAL
    assert dialog._selection_actions.GetOrientation()==wx.HORIZONTAL
    for control in (dialog.grid_step,dialog.budget_seconds,
                    dialog.controls['selection_uses_elementary_branches'],
                    dialog._scope_illustration):
        assert control.GetRect().GetRight() <= dialog._general_panel.GetClientSize().width
    for button in (dialog.gloss_button,dialog.centering_button):
        assert button.GetRect().GetBottom() <= dialog.GetClientSize().height
    wide=wx.Size(max(opening.width,dialog._wide_general_min+100),opening.height)
    dialog.SetSize(wide);dialog.Layout();dialog._on_general_size()
    assert dialog._general_columns.GetOrientation()==wx.HORIZONTAL
    dialog.SetSize(minimum);dialog.Layout();dialog._on_general_size()
    assert dialog.GetSize().width==minimum.width
    print('RESIZE PASS:',opening.width,'->',minimum.width,'->',wide.width,'->',minimum.width)
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
    select(list(groups.values()))
    dialog._on_import_centering(False)
    assert '/A' not in dialog._branch_memory.by_net
    assert dialog.centering_net_panel.net_list.GetTextValue(
        dialog.centering_net_panel.net_list.FindString('/A'),2)==''
    select([groups[branches[0]]])
    dialog._on_import_centering(False)
    assert len(dialog._branch_memory.by_net['/A'])==1
    assert reveal_calls[-1]==({'/A'},scope_list.FindString('/A'))
    select([groups[branches[1]]])
    dialog._on_import_centering(True)
    assert reveal_calls[-1]==({'/A'},scope_list.FindString('/A'))
    dialog._on_import_centering(True)
    assert reveal_calls[-1]==(set(),wx.NOT_FOUND)  # Duplicate Add must not scroll.
    assert len(dialog._branch_memory.by_net['/A'])==2
    listing=dialog.centering_net_panel.net_list
    assert listing.GetTextValue(listing.FindString('/A'),2)=='2 EB'
    # The native header adds a small border to the requested width on Windows.
    assert listing.GetTextExtent('2 EB').width <= listing.GetColumn(2).GetWidth() <= listing.FromDIP(60)
    row=listing.FindString('/A')
    for checked in (False, True):
        listing.Check(row,checked)
        event=dv.DataViewEvent(dv.EVT_DATAVIEW_ITEM_VALUE_CHANGED.typeId,listing,listing.GetColumn(0),listing.RowToItem(row))
        listing.GetEventHandler().ProcessEvent(event)
        app.ProcessPendingEvents()
        assert ('/A' in dialog.centering_net_panel.get_selected_nets())==checked
        assert dialog.centering_button.IsEnabled()==checked
        assert listing.GetTextValue(row,2)=='2 EB'
    dialog.centering_net_panel.filter_ctrl.SetValue('/A')
    assert listing.GetTextValue(listing.FindString('/A'),2)=='2 EB'
    dialog.centering_net_panel.filter_ctrl.SetValue('')
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
    assert all(listing.GetTextValue(i,2)=='' for i in range(listing.GetCount()))
    whole,_=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert len(whole[1])==sum(s.net_id==net for s in whole[0].segments)
    toggle_eb(True)
    assert listing.GetTextValue(listing.FindString('/A'),2)=='2 EB'
    assert len(dialog._branch_memory.by_net['/A'])==2
    dialog._on_clear_centering_selection(None)
    assert not dialog._branch_memory.by_net and not dialog.centering_net_panel.get_selected_nets()
    dialog.centering_net_panel.set_selected_nets(['/A'])
    whole,_=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert len(whole[1])==sum(s.net_id==net for s in whole[0].segments)
    select([groups[branches[0]]])
    dialog._on_import_centering(False)
    scope_uids=set(branches[0])
    if args.scope=='multiple':
        select([groups[branches[1]]])
        dialog._on_import_centering(True)
        scope_uids.update(branches[1])
    elif args.scope=='complete':
        for branch in branches[1:]:
            select([groups[branch]])
            dialog._on_import_centering(True)
        assert '/A' not in dialog._branch_memory.by_net
        assert listing.GetTextValue(listing.FindString('/A'),2)==''
        scope_uids={uid for uid,s in index.items() if s.net_id==net}
    elif args.scope in ('whole','eb-off'):
        if args.scope=='whole':
            dialog._on_clear_centering_selection(None)
            dialog.centering_net_panel.set_selected_nets(['/A'])
        else:
            toggle_eb(False)
        scope_uids={uid for uid,s in index.items() if s.net_id==net}
    select([groups[branches[1]]])  # Action must ignore this later live selection.
    ready,chosen=plugin._prepare_checked_nets(board,dialog,['/A'])
    assert len(ready[1])==len(scope_uids)
    fixed={t.m_Uuid.AsString():(t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth())
           for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.m_Uuid.AsString() not in scope_uids}
    before_ids={t.m_Uuid.AsString() for t in board.GetTracks()}
    if args.action=='centering':
        result=plugin._run_centering(board,dialog,dialog.values(),['/A'],prepared=ready,append_log=dialog.append_log)
        assert result and result['doors_centered']+result.get('doors_already_centered',0)==3
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
    if args.scope in ('single','multiple'):
        assert stale is None  # Replaced UUIDs must not widen the next operation.
    else:
        assert stale is not None
    dialog._branch_highlighter(())
    dialog.Destroy();app.ProcessPendingEvents();restore()
    assert hashlib.sha256(args.board.read_bytes()).hexdigest()==fingerprint
    print('PASS',args.action,args.scope,'remembered branches, Add/Replace/Clear, highlight IDs, whole-net fallback, scope column/filter, fonts, outside copper preserved; source unchanged')


if __name__=='__main__':main()
