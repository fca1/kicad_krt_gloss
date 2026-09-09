"""Integrated dialog extension: remembered elementary branches, never live seeds.

Activated by plugin startup. Historical prototype module name retained.
Memory belongs to one dialog and never writes native selection flags.
"""
from dataclasses import dataclass
from pathlib import Path


class StaleBranches(ValueError):
    pass


@dataclass(frozen=True)
class Branch:
    tracks: frozenset
    vias: frozenset = frozenset()


class BranchMemory:
    def __init__(self):
        self.by_net = {}

    def clear(self):
        self.by_net.clear()

    def import_branches(self, incoming, *, add):
        if not add:
            self.clear()
        for name, branches in incoming.items():
            previous = self.by_net.setdefault(name, [])
            for branch in branches:
                if branch.tracks and not any(old.tracks == branch.tracks for old in previous):
                    previous.append(branch)

    def describe(self, names, enabled=True):
        return '; '.join(f'{name}: {len(self.by_net[name])} EB'
                         if enabled and self.by_net.get(name) else f'{name}: whole net'
                         for name in sorted(names))

    def promote_complete_nets(self, data, index, names):
        """Normalize complete, current branch coverage to whole-net scope."""
        promoted = set()
        for name in names:
            records = self.by_net.get(name)
            if not records:
                continue
            segments = {id(s) for s in data.segments
                        if data.nets[s.net_id].name == name and not getattr(s, 'graphic', False)}
            indexed = {uid: s for uid, s in index.items() if id(s) in segments}
            saved = set().union(*(r.tracks for r in records))
            # Missing/ambiguous mappings and stale IDs must never widen the scope.
            if not segments or {id(s) for s in indexed.values()} != segments or saved != set(indexed):
                continue
            try:
                self.resolve(data, [name], index)
            except StaleBranches:
                continue
            del self.by_net[name]
            promoted.add(name)
        return promoted

    def resolve(self, data, names, uuid_to_segment, *, enabled=True):
        """Fresh objects, verified branch membership, no fallback on stale IDs."""
        from dgloss.branches import elementary_branch_segment_ids
        names = set(names)
        selected = {}
        by_id = {id(s): uid for uid, s in uuid_to_segment.items()}
        for code, net in data.nets.items():
            if net.name not in names:
                continue
            records = self.by_net.get(net.name) if enabled else None
            if not records:
                selected.update((id(s), s) for s in data.segments
                                if s.net_id == code and not getattr(s, 'graphic', False))
                continue
            for branch in records:
                if not branch.tracks <= uuid_to_segment.keys():
                    raise StaleBranches(f'{net.name}: saved tracks changed; import KiCad selection again.')
                seeds = [uuid_to_segment[uid] for uid in branch.tracks]
                if any(s.net_id != code for s in seeds):
                    raise StaleBranches(f'{net.name}: saved branch changed net; import again.')
                current, count = elementary_branch_segment_ids(data, seeds)
                if count != 1 or {by_id.get(i) for i in current} != set(branch.tracks):
                    raise StaleBranches(f'{net.name}: branch topology changed; import again.')
                selected.update((id(s), s) for s in seeds)
        return list(selected.values())




def thin_overlay_lines(changes):
    """Only new track copies are 0.1 mm; old dashes/vias retain their policy."""
    for change in changes.get('segments') or []:
        new = change.get('new')
        if new is not None:
            yield (new.start_x, new.start_y), (new.end_x, new.end_y), 0.1
    # Reuse the unmodified generator without its new-track entries.
    rest = dict(changes)
    rest['segments'] = [{'old': c['old']} for c in changes.get('segments') or [] if c.get('old') is not None]
    yield from _original_overlay_lines(rest)


from .debug_overlay import overlay_lines as _original_overlay_lines


def activate(action_module, *, board_provider=None):
    """Startup wiring; returns a restore function for detached tests."""
    import wx
    bridge = action_module.KICAD
    base_dialog = action_module.GlossSettingsDialog
    plugin = action_module.KiCadKrtGlossPlugin
    old_prepare = plugin._prepare_checked_nets
    from . import debug_overlay, gloss_visualization
    old_overlay = debug_overlay.overlay_lines
    old_native_overlay = gloss_visualization.overlay_lines
    debug_overlay.overlay_lines = thin_overlay_lines
    gloss_visualization.overlay_lines = thin_overlay_lines

    class BranchDialog(base_dialog):
        def __init__(self, *args, **kwargs):
            self._branch_board = (board_provider or bridge.active_board)()
            self._branch_memory = BranchMemory()
            self._branch_highlighter = bridge.branch_highlighter(
                self._branch_board, self._branch_memory)
            kwargs['on_net_selection_changed'] = self._preview_branches
            super().__init__(*args, **kwargs)
            from .branch_scope_list import install
            install(self)
            panel = self.notebook.GetPage(0)
            def enlarge(sizer):
                for child in sizer.GetChildren():
                    window = child.GetWindow()
                    if window in (self.grid_step, self.budget_seconds):
                        window.SetFont(self.centering_proximity_mm.GetFont())
                        window.InvalidateBestSize()
                        window.SetMinSize(window.GetBestSize())
                    elif child.GetSizer():
                        enlarge(child.GetSizer())

            def find_calculation(sizer):
                if isinstance(sizer, wx.StaticBoxSizer) and sizer.GetStaticBox().GetLabel() == 'Calculation Settings / Execution Limit':
                    enlarge(sizer)
                    rows = [item.GetSizer() for item in sizer.GetChildren()]
                    grid = wx.FlexGridSizer(cols=3, hgap=8, vgap=8)
                    grid.AddGrowableCol(0)
                    width = max(self.grid_step.GetBestSize().width, self.budget_seconds.GetBestSize().width)
                    for row in rows:
                        windows = [item.GetWindow() for item in row.GetChildren()]
                        for window in windows:
                            row.Detach(window)
                        label, control = windows[:2]
                        control.SetMinSize((width, control.GetBestSize().height))
                        grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                        grid.Add(control, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
                        if len(windows) == 3:
                            grid.Add(windows[2], 0, wx.ALIGN_CENTER_VERTICAL)
                        else:
                            grid.AddSpacer(0)
                    sizer.Clear()
                    sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 8)
                    return
                for child in sizer.GetChildren():
                    if child.GetSizer():
                        find_calculation(child.GetSizer())
            find_calculation(panel.GetSizer())
            def find_illustration(sizer):
                for child in sizer.GetChildren():
                    window = child.GetWindow()
                    if isinstance(window, wx.StaticBitmap):
                        return window
                    if child.GetSizer():
                        found = find_illustration(child.GetSizer())
                        if found is not None:
                            return found
                return None
            self._scope_illustration = find_illustration(panel.GetSizer())
            if self._scope_illustration is not None:
                branch_bitmap = self._scope_illustration.GetBitmap()
                net_image = wx.Image(str(Path(__file__).parent / 'img_dlg' / 'selection_net_illustration.png'))
                if not net_image.IsOk():
                    raise ValueError('Missing whole-net selection illustration')
                self._scope_bitmaps = {
                    True: branch_bitmap,
                    False: wx.Bitmap(net_image.Scale(branch_bitmap.GetWidth(), branch_bitmap.GetHeight(), wx.IMAGE_QUALITY_HIGH)),
                }
            self._branch_summary = wx.StaticText(panel, label='', style=wx.ST_NO_AUTORESIZE)
            self._branch_summary.SetMinSize((1, self._branch_summary.GetCharHeight()))
            panel.GetSizer().Add(self._branch_summary, 0, wx.EXPAND | wx.ALL, 8)
            self.controls['selection_uses_elementary_branches'].Bind(
                wx.EVT_CHECKBOX, lambda event: self._sync_net_selection())
            self.Bind(wx.EVT_CLOSE, self._close_branch_preview)
            # Preserve the initial multi-net native seeds too.
            if self._eb_enabled():
                self._capture_branches(add=True, update_checks=False)
            self._sync_net_selection()
            self._configure_dialog_size()

        def _eb_enabled(self):
            return self.controls['selection_uses_elementary_branches'].GetValue()

        def _preview_branches(self, names):
            enabled = self._eb_enabled()
            net_list = self.centering_net_panel.net_list
            if hasattr(net_list, 'refresh_scope'):
                net_list.refresh_scope()
            if getattr(self, '_scope_illustration', None) is not None:
                self._scope_illustration.SetBitmap(self._scope_bitmaps[enabled])
                self._scope_illustration.Refresh()
            self._branch_highlighter(names, enabled)
            if hasattr(self, '_branch_summary'):
                description = self._branch_memory.describe(names, enabled)
                self._branch_summary.SetLabel(description)
                self._branch_summary.SetToolTip(description)
                self.notebook.GetPage(0).Layout()

        def _capture_branches(self, *, add, update_checks=True):
            try:
                def state():
                    checked = set(self.centering_net_panel.get_selected_nets())
                    return {name: (name in checked, frozenset(self._branch_memory.by_net.get(name, ())))
                            for name in checked | self._branch_memory.by_net.keys()}
                before = state()
                data = bridge.build_pcb_data(self._branch_board)
                allowed = {name for name, _ in plugin._modifiable_net_rows(self._branch_board, data)}
                if self._eb_enabled():
                    index = bridge.branch_track_index(self._branch_board, data)
                    incoming = bridge.capture_branches(self._branch_board, data, index, allowed)
                    self._branch_memory.import_branches(incoming, add=add)
                    self._branch_memory.promote_complete_nets(data, index, incoming)
                else:
                    incoming = {name: [] for name in bridge.selected_net_names(self._branch_board) if name in allowed}
                    if not add:
                        self._branch_memory.clear()
                names = set(incoming)
                if add:
                    names.update(self.centering_net_panel.get_selected_nets())
                if update_checks:
                    self.centering_net_panel.set_selected_nets(names)
                    self._clear_centering_highlight()
                self._sync_net_selection()
                if update_checks:
                    after = state()
                    empty = (False, frozenset())
                    changed = {name for name in before.keys() | after.keys()
                               if before.get(name, empty) != after.get(name, empty)}
                    self.centering_net_panel.net_list.reveal_first_changed(changed)
            except StaleBranches as exc:
                self.centering_status.SetLabel(str(exc))

        def _on_import_centering(self, add):
            self._capture_branches(add=add)

        def _on_clear_centering_selection(self, event):
            self._branch_memory.clear()
            super()._on_clear_centering_selection(event)
            self._sync_net_selection()

        def _close_branch_preview(self, event):
            self._branch_highlighter(())
            event.Skip()

    def prepare_checked(self, board, parent, names):
        if not isinstance(parent, BranchDialog):
            return old_prepare(self, board, parent, names)
        if not names:
            return None, []
        prepared = self._prepare_selection(board, parent)
        if prepared is None:
            return None, []
        data, _live_seeds = prepared
        rows = self._modifiable_net_rows(board, data)
        chosen = {code for name, code in rows if name in names}
        names = {name for name, code in rows if code in chosen}
        if not chosen:
            return None, []
        try:
            needs_branches = parent._eb_enabled() and any(parent._branch_memory.by_net.get(name) for name in names)
            index = bridge.branch_track_index(board, data) if needs_branches else {}
            seeds = parent._branch_memory.resolve(data, names, index, enabled=parent._eb_enabled())
        except StaleBranches as exc:
            parent.append_log('\nEB scope cancelled: '+str(exc)+'\n')
            parent.centering_status.SetLabel(str(exc))
            parent._preview_branches(names)
            return None, []
        parent.append_log('\nRemembered scope: '+parent._branch_memory.describe(names, parent._eb_enabled())+'\n')
        return (data, seeds), sorted(chosen)

    action_module.GlossSettingsDialog = BranchDialog
    plugin._prepare_checked_nets = prepare_checked

    def restore():
        action_module.GlossSettingsDialog = base_dialog
        plugin._prepare_checked_nets = old_prepare
        debug_overlay.overlay_lines = old_overlay
        gloss_visualization.overlay_lines = old_native_overlay
    return restore
