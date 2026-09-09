"""Opt-in dialog prototype: remembered elementary branches, never live seeds.

Not imported by the normal plugin. Call activate(action_plugin) to try it.
Memory belongs to one dialog and never writes native selection flags.
"""
from collections import defaultdict
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


def track_index(board, data, pcbnew):
    """Match native UUIDs to this import without relying on object lifetimes."""
    from .board_adapter import _native_segment_key, _segment_key
    buckets = defaultdict(list)
    for s in data.segments:
        if not getattr(s, 'graphic', False):
            buckets[_segment_key(s)].append(s)
    result = {}
    for item in board.GetTracks():
        if item.GetClass() != 'PCB_TRACK':
            continue
        matches = buckets.get(_native_segment_key(board, pcbnew, item), [])
        if len(matches) > 1:
            # Do not let ambiguity on an unrelated net block this import.
            # A selected or remembered UUID absent from the index fails closed.
            continue
        if matches:
            result[item.m_Uuid.AsString()] = matches[0]
    return result


def capture(board, data, index, pcbnew, allowed_names):
    from dgloss.branches import elementary_branch_segment_ids
    by_id = {id(s): uid for uid, s in index.items()}
    incoming = defaultdict(list)
    covered = set()
    for track in board.GetTracks():
        if track.GetClass() != 'PCB_TRACK' or not track.IsSelected():
            continue
        seed = index.get(track.m_Uuid.AsString())
        if seed is None:
            raise StaleBranches('Selected track could not be imported; selection unchanged.')
        name = data.nets[seed.net_id].name
        if name not in allowed_names or id(seed) in covered:
            continue
        ids, _count = elementary_branch_segment_ids(data, [seed])
        if not ids <= by_id.keys():
            raise StaleBranches(f'{name}: branch has unmapped copper; import cancelled.')
        covered.update(ids)
        points = {(round(x, 6), round(y, 6)) for s in data.segments if id(s) in ids
                  for x, y in ((s.start_x, s.start_y), (s.end_x, s.end_y))}
        vias = frozenset(item.m_Uuid.AsString() for item in board.GetTracks()
                         if item.GetClass() == 'PCB_VIA' and item.GetNetCode() == seed.net_id
                         and (round(float(pcbnew.ToMM(item.GetPosition().x)), 6),
                              round(float(pcbnew.ToMM(item.GetPosition().y)), 6)) in points)
        incoming[name].append(Branch(frozenset(by_id[i] for i in ids), vias))
    return dict(incoming)


class BranchHighlighter:
    """The same renderer-visible brightening as production, with UUID filtering."""
    def __init__(self, board, refresh, memory):
        self.board, self.refresh, self.memory = board, refresh, memory
        self.owned = set()

    def __call__(self, names, enabled=True):
        names = set(names)
        items = list(self.board.GetTracks())
        items += [p for f in self.board.GetFootprints() for p in f.Pads()]
        items += list(self.board.Zones())
        present = {i.m_Uuid.AsString() for i in items}
        codes = {code: net.GetNetname() for code, net in self.board.GetNetsByNetcode().items()}
        allowed = {}
        for name in names:
            records = self.memory.by_net.get(name) if enabled else None
            if records:
                tracks = set().union(*(r.tracks for r in records))
                allowed[name] = (tracks | set().union(*(r.vias for r in records))
                                 if tracks <= present else set())
            else:
                allowed[name] = None
        owned = set()
        for item in items:
            uid = item.m_Uuid.AsString()
            name = codes.get(item.GetNetCode())
            chosen = name in allowed and (allowed[name] is None or uid in allowed[name])
            if chosen:
                if uid in self.owned or not item.IsBrightened():
                    item.SetBrightened()
                    owned.add(uid)
            elif uid in self.owned:
                item.ClearBrightened()
        self.owned = owned
        self.refresh()


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
    """Opt-in runtime wiring; returns a restore function for detached tests."""
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
            self._branch_highlighter = BranchHighlighter(
                self._branch_board, bridge.refresh, self._branch_memory)
            kwargs['on_net_selection_changed'] = self._preview_branches
            super().__init__(*args, **kwargs)
            panel = self.notebook.GetPage(0)
            def enlarge(sizer):
                for child in sizer.GetChildren():
                    window = child.GetWindow()
                    if window:
                        window.SetFont(self.centering_proximity_mm.GetFont())
                        window.InvalidateBestSize()
                        window.SetMinSize(window.GetBestSize())
                    elif child.GetSizer():
                        enlarge(child.GetSizer())

            def find_calculation(sizer):
                if isinstance(sizer, wx.StaticBoxSizer) and sizer.GetStaticBox().GetLabel() == 'Calculation Settings / Execution Limit':
                    sizer.GetStaticBox().SetFont(self.centering_proximity_mm.GetFont().Bold())
                    enlarge(sizer)
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
            self._branch_summary = wx.StaticText(panel, label='')
            panel.GetSizer().Add(self._branch_summary, 0, wx.EXPAND | wx.ALL, 8)
            self.controls['selection_uses_elementary_branches'].Bind(
                wx.EVT_CHECKBOX, lambda event: self._sync_net_selection())
            self.Bind(wx.EVT_CLOSE, self._close_branch_preview)
            # Preserve the initial multi-net native seeds too.
            if self._eb_enabled():
                self._capture_branches(add=True, update_checks=False)
            self._sync_net_selection()
            self.Fit()
            self.SetMinSize(self.GetSize())
            self.Layout()

        def _eb_enabled(self):
            return self.controls['selection_uses_elementary_branches'].GetValue()

        def _preview_branches(self, names):
            enabled = self._eb_enabled()
            if getattr(self, '_scope_illustration', None) is not None:
                self._scope_illustration.SetBitmap(self._scope_bitmaps[enabled])
                self._scope_illustration.Refresh()
            self._branch_highlighter(names, enabled)
            if hasattr(self, '_branch_summary'):
                self._branch_summary.SetLabel(self._branch_memory.describe(names, enabled))
                self._branch_summary.Wrap(650)
                self.notebook.GetPage(0).Layout()

        def _capture_branches(self, *, add, update_checks=True):
            try:
                data = bridge.build_pcb_data(self._branch_board)
                allowed = {name for name, _ in plugin._modifiable_net_rows(self._branch_board, data)}
                if self._eb_enabled():
                    index = track_index(self._branch_board, data, bridge._pcbnew())
                    incoming = capture(self._branch_board, data, index, bridge._pcbnew(), allowed)
                    self._branch_memory.import_branches(incoming, add=add)
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
            index = track_index(board, data, bridge._pcbnew()) if needs_branches else {}
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
