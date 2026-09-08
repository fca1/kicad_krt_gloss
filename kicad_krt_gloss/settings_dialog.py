"""Standalone Gloss settings and independent Centering action."""

import os
from types import SimpleNamespace
import wx
import wx.adv
from wx.lib.buttons import GenButton

from .version import __version__


_DIALOG_IMAGES = os.path.join(os.path.dirname(__file__), "img_dlg")


GENERAL_DEFAULTS = {
    "selection_uses_elementary_branches": True,
    "grid_step": 0.1,
    "budget_seconds": 20.0,
}

GLOSS_DEFAULTS = {
    "move_vias": True,
    "repeat_until_stable": True,
    "g4_max_passes": 1,
}

CENTERING_DEFAULTS = {
    "centering_proximity_mm": 1.0,
}

DEFAULTS = GENERAL_DEFAULTS | GLOSS_DEFAULTS | CENTERING_DEFAULTS


class GlossSettingsDialog(wx.Dialog):
    def __init__(self, parent, values, selected_count, *, on_gloss=None,
                 on_centering=None, pcb_data=None, centering_nets=(),
                 preselected_centering_nets=(), initial_tab=None,
                 initial_log="", on_import_centering=None,
                 on_refresh_proximity=None, on_net_selection_changed=None):
        super().__init__(
            parent, title="KiCad KRT Gloss",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.STAY_ON_TOP)
        values = dict(values or {})
        if "move_vias" not in values and "enable_g3_1" in values:
            values["move_vias"] = values["enable_g3_1"]
        values = dict(DEFAULTS, **values)
        self._on_gloss_callback = on_gloss
        self._on_centering_callback = on_centering
        self._on_import_centering_callback = on_import_centering
        self._on_refresh_proximity_callback = on_refresh_proximity
        self._selected_count = selected_count
        self._on_net_selection_changed = on_net_selection_changed
        wx.ToolTip.SetDelay(250)
        wx.ToolTip.SetAutoPop(15000)
        wx.ToolTip.SetReshow(50)
        self.notebook = wx.Notebook(self)
        panel = wx.Panel(self.notebook)
        content = wx.BoxSizer(wx.VERTICAL)
        self.controls = {}

        general_columns = wx.BoxSizer(wx.HORIZONTAL)
        left_column = wx.BoxSizer(wx.VERTICAL)
        right_column = wx.BoxSizer(wx.VERTICAL)
        right_box = wx.StaticBox(panel, label="Select branch")
        selection = wx.StaticBoxSizer(right_box, wx.VERTICAL)
        selected_net = wx.StaticText(
            panel, label="Selected Nets: 0")
        self.selected_net_label = selected_net
        selected_font = selected_net.GetFont()
        selected_font.SetPointSize(selected_font.GetPointSize() + 4)
        selected_font.SetWeight(wx.FONTWEIGHT_BOLD)
        selected_net.SetFont(selected_font)
        selection.Add(selected_net, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        key = "selection_uses_elementary_branches"
        control = wx.CheckBox(panel, label="Use elementary branches")
        control.SetValue(bool(values[key]))
        branch_help = (
            "When enabled, each selected track segment designates its complete "
            "elementary branch, bounded by pads, free ends or T/X junctions. "
            "When disabled, the complete nets containing the selected segments "
            "are processed.")
        control.SetToolTip(branch_help)
        self.controls[key] = control
        illustration_path = os.path.join(
            _DIALOG_IMAGES, "selection_scope_illustration.png")
        if os.path.exists(illustration_path):
            image = wx.Image(illustration_path, wx.BITMAP_TYPE_PNG)
            illustration = wx.StaticBitmap(panel, bitmap=wx.Bitmap(image))
            illustration.SetToolTip(branch_help)
            selection.Add(illustration, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        selection.Add(control, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        calculation_box = wx.StaticBox(panel, label="Calculation Settings / Execution Limit")
        calculation = wx.StaticBoxSizer(calculation_box, wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        grid_label = wx.StaticText(panel, label="KRT grid step (mm):")
        row.Add(grid_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.grid_step = wx.SpinCtrlDouble(
            panel, min=0.01, max=2.0, initial=float(values["grid_step"]),
            inc=0.01, size=(100, -1))
        self.grid_step.SetDigits(3)
        grid_help = (
            "Set the KRT search-grid resolution in millimetres. Length-reduction "
            "operations must save strictly more than this value, and generated "
            "micro-segments shorter than one grid step are rejected. A smaller "
            "step can find finer improvements but may take longer.")
        grid_label.SetToolTip(grid_help)
        self.grid_step.SetToolTip(grid_help)
        row.Add(self.grid_step, 0)
        calculation.Add(row, 0, wx.ALL, 8)


        budget_row = wx.BoxSizer(wx.HORIZONTAL)
        budget_label = wx.StaticText(panel, label="Time budget:")
        budget_row.Add(budget_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.budget_seconds = wx.SpinCtrlDouble(
            panel, min=10.0, max=240.0,
            initial=float(values["budget_seconds"]), inc=10.0,
            size=(90, -1))
        self.budget_seconds.SetDigits(0)
        budget_help = (
            "Maximum time allocated to the initial Gloss optimization pass, "
            "excluding G4. G4 uses its own pass-count and convergence limits. KRT "
            "preprocessing, final validation and applying the result may make "
            "the total runtime longer.")
        budget_label.SetToolTip(budget_help)
        self.budget_seconds.SetToolTip(budget_help)
        budget_row.Add(self.budget_seconds, 0)
        budget_unit = wx.StaticText(panel, label="s")
        budget_unit.SetToolTip(budget_help)
        budget_row.Add(budget_unit, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        calculation.Add(budget_row, 0, wx.ALL, 8)
        centering_selection = self._create_centering_selection(
            panel, pcb_data, centering_nets, preselected_centering_nets)
        left_column.Add(centering_selection, 1, wx.EXPAND | wx.BOTTOM, 8)
        right_column.Add(selection, 0, wx.EXPAND | wx.BOTTOM, 8)
        right_column.Add(calculation, 0, wx.EXPAND)
        general_columns.Add(left_column, 1, wx.EXPAND | wx.ALL, 8)
        general_columns.Add(right_column, 0, wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM, 8)
        content.Add(general_columns, 1, wx.EXPAND)
        panel.SetSizer(content)
        self.notebook.AddPage(panel, "General")

        self._create_gloss_tab(values)
        self._create_centering_tab(values)

        log_panel = wx.Panel(self.notebook)
        log_content = wx.BoxSizer(wx.VERTICAL)
        self.log_text = wx.TextCtrl(
            log_panel, value=initial_log,
            style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 |
                   wx.HSCROLL | wx.VSCROLL | wx.ALWAYS_SHOW_SB),
            size=(650, 340))
        self.log_text.SetFont(wx.Font(
            10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL))
        log_content.Add(self.log_text, 1, wx.EXPAND | wx.ALL, 5)
        log_buttons = wx.BoxSizer(wx.HORIZONTAL)
        log_buttons.AddStretchSpacer()
        copy_log = wx.Button(log_panel, label="Copy Log")
        copy_log.SetToolTip("Copy all Track Gloss log output to the clipboard.")
        copy_log.Bind(wx.EVT_BUTTON, self._on_copy_log)
        clear_log = wx.Button(log_panel, label="Clear Log")
        clear_log.SetToolTip("Clear all Track Gloss log output.")
        clear_log.Bind(wx.EVT_BUTTON, self._on_clear_log)
        log_buttons.Add(copy_log, 0, wx.RIGHT, 5)
        log_buttons.Add(clear_log, 0)
        log_content.Add(log_buttons, 0, wx.EXPAND | wx.RIGHT | wx.BOTTOM, 5)
        log_panel.SetSizer(log_content)
        self.notebook.AddPage(log_panel, "Log")

        about = wx.Panel(self.notebook)
        about_content = wx.BoxSizer(wx.VERTICAL)
        about_content.AddSpacer(16)
        icon_path = os.path.join(os.path.dirname(__file__), "icon_64.png")
        if os.path.exists(icon_path):
            image = wx.Image(icon_path, wx.BITMAP_TYPE_PNG)
            bitmap = wx.StaticBitmap(about, bitmap=wx.Bitmap(image))
            about_content.Add(bitmap, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        title = wx.StaticText(about, label="KiCad KRT Gloss")
        title.SetFont(title.GetFont().Bold())
        about_content.Add(title, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        info = wx.FlexGridSizer(cols=2, hgap=12, vgap=6)
        rows = (
            ("KRG version:", __version__, None),
            ("KRT version:", self._krt_version(), None),
            ("Author:", "Frantz",
             "https://github.com/fca1/kicad_krt_gloss"),
            ("Co-author:", "ChatGPT/Codex (OpenAI)", None),
            (None, None, None),
            ("KRT author:", "DrAndyHaas",
            "https://github.com/drandyhaas/KiCadRoutingTools"),
        )
        for label, value, url in rows:
            if label is None:
                info.AddSpacer(10)
                info.AddSpacer(10)
                continue
            name = wx.StaticText(about, label=label)
            name.SetFont(name.GetFont().Bold())
            info.Add(name, 0, wx.ALIGN_RIGHT)
            value_row = wx.BoxSizer(wx.HORIZONTAL)
            value_row.Add(wx.StaticText(about, label=value), 0,
                          wx.ALIGN_CENTER_VERTICAL)
            if url:
                value_row.Add(wx.adv.HyperlinkCtrl(
                    about, label="GitHub Repository", url=url), 0,
                    wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
            info.Add(value_row, 0, wx.ALIGN_LEFT)
        about_content.Add(info, 0, wx.ALIGN_CENTER | wx.ALL, 12)
        license_text = wx.StaticText(about, label="Open source — MIT License")
        license_text.SetForegroundColour(wx.Colour(128, 128, 128))
        about_content.Add(license_text, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        about_content.AddStretchSpacer()
        about.SetSizer(about_content)
        self.notebook.AddPage(about, "About")

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.notebook, 1, wx.EXPAND)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.gloss_button = wx.Button(self, label="Gloss")
        self.gloss_button.SetToolTip("Run Track Gloss with these settings.")
        self.gloss_button.Bind(wx.EVT_BUTTON, self._on_gloss)
        self.centering_button = GenButton(self, label="Centering")
        self.centering_button.SetBackgroundColour(wx.Colour(205, 229, 250))
        self.centering_button.SetForegroundColour(wx.Colour(20, 45, 65))
        self.centering_button.SetToolTip(
            "Run corridor Gloss followed by Centering on the checked nets.")
        self.centering_button.Bind(wx.EVT_BUTTON, self._on_centering)
        close_button = wx.Button(self, label="Close")
        close_button.SetToolTip("Close this dialog.")
        close_button.Bind(wx.EVT_BUTTON, lambda _event: self.Close())
        buttons.Add(self.gloss_button, 1, wx.RIGHT, 5)
        buttons.Add(self.centering_button, 1, wx.RIGHT, 5)
        buttons.Add(close_button, 1)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())
        self.centering_net_panel.set_selection_changed_callback(self._sync_net_selection)
        self.centering_net_panel.net_list.Bind(
            wx.EVT_LISTBOX, self._on_centering_net_row_selected)
        self.centering_net_panel.net_list.Bind(
            wx.EVT_CHECKLISTBOX, self._on_centering_net_checked)
        self._sync_net_selection()
        if initial_tab:
            for index in range(self.notebook.GetPageCount()):
                if self.notebook.GetPageText(index) == initial_tab:
                    self.notebook.SetSelection(index)
                    break
        self.Bind(wx.EVT_SHOW, self._on_initial_show)

    def _create_gloss_tab(self, values):
        """Build the page containing options used only by the Gloss action."""
        panel = wx.Panel(self.notebook)
        content = wx.BoxSizer(wx.VERTICAL)
        operations_box = wx.StaticBox(panel, label="Gloss Operations")
        operations = wx.StaticBoxSizer(operations_box, wx.VERTICAL)
        visible_options = (
            ("move_vias", "Movable vias",
             "Move an eligible unlocked via connected to exactly two unlocked "
             "track segments on different copper layers. Both local and complete "
             "track-chain searches obey this option. The via diameter, drill, type, "
             "net and layer span remain unchanged. The move is accepted only "
             "when it saves more than one grid step and passes KRT clearance "
             "and connectivity checks.", "via"),
        )
        for key, label, tooltip, illustration in visible_options:
            control = wx.CheckBox(panel, label=label)
            control.SetValue(bool(values[key]))
            control.SetToolTip(tooltip)
            self.controls[key] = control
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.Add(control, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
            row.Add(self._create_gloss_illustration(
                panel, illustration, tooltip), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)
            operations.Add(row, 0, wx.EXPAND | wx.BOTTOM, 8)
        repeat = wx.CheckBox(panel, label="G4 — Repeat Gloss until stable")
        repeat.SetValue(bool(values["repeat_until_stable"]))
        repeat.SetToolTip(
            "Run additional Gloss passes until no further change is found, "
            "within the configured G4 pass limit and gain threshold. "
            "Each additional whole-board pass can take significant time. "
            "Local autogloss remains active when "
            "this option is disabled.")
        self.controls["repeat_until_stable"] = repeat
        operations.Add(repeat, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        g4_passes = wx.BoxSizer(wx.HORIZONTAL)
        g4_passes.Add(wx.StaticText(panel, label="G4 passes:"), 0,
                      wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.g4_max_passes = wx.SpinCtrl(
            panel, min=1, max=10, initial=int(values["g4_max_passes"]),
            size=(70, -1))
        g4_passes_help = (
            "Maximum number of additional whole-board G4 passes after the "
            "initial Gloss pass. The G4 checkbox must be enabled.")
        self.g4_max_passes.SetToolTip(g4_passes_help)
        g4_passes.Add(self.g4_max_passes, 0)
        operations.Add(g4_passes, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        if self._selected_count == 1:
            repeat.Disable()
            self.g4_max_passes.Disable()
        content.Add(operations, 0, wx.EXPAND | wx.ALL, 8)
        content.AddStretchSpacer()
        panel.SetSizer(content)
        self.notebook.AddPage(panel, "Gloss")

    @staticmethod
    def _create_gloss_illustration(parent, kind, tooltip):
        """Load the packaged illustration; no geometry is drawn at runtime."""
        image_path = os.path.join(_DIALOG_IMAGES, f"{kind}_illustration.png")
        image = wx.Image(image_path, wx.BITMAP_TYPE_PNG)
        diagram = wx.StaticBitmap(parent, bitmap=wx.Bitmap(image))
        diagram.SetToolTip(tooltip)
        return diagram

    def _create_centering_selection(self, panel, pcb_data, centering_nets,
                                    preselected_nets):
        """Build the shared Centering net checklist on the General page."""
        net_box = wx.StaticBox(panel, label="Net Selection")
        net_sizer = wx.StaticBoxSizer(net_box, wx.VERTICAL)
        from dgloss.krt_api import NetSelectionPanel
        if pcb_data is None:
            pcb_data = SimpleNamespace(nets={}, pads_by_net={}, footprints={})
        self.centering_net_panel = NetSelectionPanel(
            panel, pcb_data,
            instructions=("Click a net to highlight it in KiCad; check nets "
                          "for Gloss and Centering..."),
            show_hide_checkbox=False,
            show_hide_differential=False,
            show_component_filter=True,
            show_component_dropdown=True,
            min_pads_for_dropdown=3,
        )
        self.centering_net_panel.all_nets = list(centering_nets)
        self.centering_net_panel.refresh(sync_from_visible=False)
        self.centering_net_panel.set_selected_nets(preselected_nets)
        net_sizer.Add(self.centering_net_panel, 1, wx.EXPAND)

        selection_actions = wx.BoxSizer(wx.HORIZONTAL)
        add_selection = wx.Button(panel, label="Add KiCad selection")
        add_selection.SetToolTip(
            "Check the nets of currently selected KiCad tracks, keeping "
            "the nets already checked here.")
        add_selection.Bind(wx.EVT_BUTTON,
                           lambda _event: self._on_import_centering(True))
        replace_selection = wx.Button(panel, label="Replace with KiCad selection")
        replace_selection.SetToolTip(
            "Check only the nets of currently selected KiCad tracks.")
        replace_selection.Bind(
            wx.EVT_BUTTON,
            lambda _event: self._on_import_centering(False))
        clear_selection = wx.Button(panel, label="Clear selection")
        clear_selection.SetToolTip("Uncheck every net for Gloss and Centering.")
        clear_selection.Bind(wx.EVT_BUTTON, self._on_clear_centering_selection)
        selection_actions.Add(add_selection, 1, wx.RIGHT, 5)
        selection_actions.Add(replace_selection, 1, wx.RIGHT, 5)
        selection_actions.Add(clear_selection, 1)
        net_sizer.Add(selection_actions, 0, wx.EXPAND | wx.TOP, 5)
        wx.CallAfter(self._clear_centering_highlight)
        return net_sizer

    def _create_centering_tab(self, values):
        """Build the special G3.6 controls without duplicating net selection."""
        panel = wx.Panel(self.notebook)
        content = wx.BoxSizer(wx.VERTICAL)

        options = wx.BoxSizer(wx.VERTICAL)
        icon_path = os.path.join(_DIALOG_IMAGES, "centering_illustration.png")
        self.centering_proximity_mm = wx.SpinCtrlDouble(
            panel, min=0.0, max=5.0,
            initial=float(values["centering_proximity_mm"]), inc=0.1)
        self.centering_proximity_mm.SetDigits(2)
        self.centering_proximity_mm.SetToolTip(
            "Maximum absolute proximity to obstacles, in millimetres.")
        if os.path.exists(icon_path):
            image = wx.Image(icon_path, wx.BITMAP_TYPE_PNG)
            bitmap = wx.Bitmap(image)
            diagram = wx.Panel(panel, size=bitmap.GetSize())
            diagram.SetBackgroundStyle(wx.BG_STYLE_PAINT)

            def paint_diagram(_event):
                """Draw the diagram behind its overlaid input control."""
                dc = wx.AutoBufferedPaintDC(diagram)
                dc.DrawBitmap(bitmap, 0, 0, True)

            diagram.Bind(wx.EVT_PAINT, paint_diagram)
            # The diagram already names this value.  Place the editor directly
            # beside that label so the value and its visual meaning stay together.
            self.centering_proximity_mm.Reparent(diagram)
            self.centering_proximity_mm.SetPosition((123, 31))
            self.centering_proximity_mm.SetSize((52, -1))
            proximity_title = wx.StaticText(panel, label="Proximity max")
            proximity_title.SetFont(proximity_title.GetFont().Bold())
            options.Add(proximity_title, 0, wx.ALIGN_CENTER | wx.TOP, 10)
            options.Add(diagram, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        else:
            # Keep the setting reachable if the optional illustration is absent.
            options.Add(self.centering_proximity_mm, 0,
                        wx.ALIGN_CENTER | wx.ALL, 10)

        refresh_proximity = wx.Button(panel, label="Refresh")
        refresh_proximity.SetToolTip(
            "Set Proximity max from exactly two selected KiCad pads when "
            "their centre spacing is between 0 and 5 mm.")
        refresh_proximity.Bind(wx.EVT_BUTTON, self._on_refresh_proximity)
        options.Add(refresh_proximity, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        options.AddStretchSpacer()
        content.Add(options, 1, wx.ALIGN_CENTER | wx.ALL, 8)

        self.centering_status = wx.StaticText(panel, label="Ready.")
        content.Add(self.centering_status, 0,
                    wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(content)
        self.notebook.AddPage(panel, "Centering")

    def _on_clear_log(self, _event):
        self.log_text.Clear()

    def _sync_net_selection(self):
        names = self.centering_net_panel.get_selected_nets()
        self.selected_net_label.SetLabel(f"Selected Nets: {len(names)}")
        self.gloss_button.Enable(bool(names))
        self.centering_button.Enable(bool(names))
        self.controls["repeat_until_stable"].Enable(len(names) > 1)
        self.g4_max_passes.Enable(len(names) > 1)
        if self._on_net_selection_changed is not None:
            self._on_net_selection_changed(names)

    def _on_centering_net_row_selected(self, event):
        """Preview the clicked net without changing the checked action scope."""
        net_list = self.centering_net_panel.net_list
        names = [net_list.GetString(index)
                 for index in net_list.GetSelections()]
        if names and self._on_net_selection_changed is not None:
            self._on_net_selection_changed(names)
        event.Skip()

    def _on_centering_net_checked(self, event):
        """Apply the checklist scope after wx has updated the check state."""
        wx.CallAfter(self._sync_net_selection)
        event.Skip()

    def _on_import_centering(self, add):
        """Merge or replace checked Centering nets from the KiCad selection."""
        if self._on_import_centering_callback is None:
            return
        imported = set(self._on_import_centering_callback() or ())
        if add:
            imported.update(self.centering_net_panel.get_selected_nets())
        self.centering_net_panel.set_selected_nets(imported)
        self._clear_centering_highlight()
        selected = self.centering_net_panel.get_selected_nets()
        verb = "Added" if add else "Replaced"
        self.centering_status.SetLabel(
            f"{verb} from KiCad selection: {len(selected)} net(s) checked.")

    def _on_clear_centering_selection(self, _event):
        """Clear the Centering net checklist without affecting KiCad."""
        self.centering_net_panel.set_selected_nets(())
        self._clear_centering_highlight()
        self.centering_status.SetLabel("Net selection cleared.")

    def _clear_centering_highlight(self):
        """Do not show every initial checklist row as a blue selection."""
        net_list = self.centering_net_panel.net_list
        for index in net_list.GetSelections():
            net_list.Deselect(index)

    def _on_initial_show(self, event):
        if event.IsShown():
            self.Unbind(wx.EVT_SHOW, handler=self._on_initial_show)
            wx.CallAfter(self._center_net_list_scroll)
        event.Skip()

    def _center_net_list_scroll(self):
        """Start halfway through the scrollable range without checking a net."""
        if not self:
            return
        net_list = self.centering_net_panel.net_list
        count = net_list.GetCount()
        if count:
            visible = max(1, net_list.GetCountPerPage())
            net_list.SetFirstItem(max(0, (count - visible) // 2))

    def _on_refresh_proximity(self, _event):
        """Refresh Proxi only from one exclusive native two-pad selection."""
        if self._on_refresh_proximity_callback is None:
            return
        distance = self._on_refresh_proximity_callback()
        if distance is None:
            self.centering_status.SetLabel(
                "Select exactly two pads in KiCad to refresh Proxi.")
        elif 0.0 <= distance <= 5.0:
            self.centering_proximity_mm.SetValue(distance)
            self.centering_status.SetLabel(
                f"Proxi refreshed from pad spacing: {distance:.2f} mm.")
        else:
            self.centering_status.SetLabel(
                "Selected pad spacing is outside the 0–5 mm Proxi range.")

    def _on_copy_log(self, _event):
        if not wx.TheClipboard.Open():
            wx.MessageBox("The clipboard is unavailable.", "Copy Log",
                          wx.OK | wx.ICON_WARNING)
            return
        try:
            wx.TheClipboard.SetData(wx.TextDataObject(self.log_text.GetValue()))
            wx.TheClipboard.Flush()
        finally:
            wx.TheClipboard.Close()

    def _show_action_tab(self, name):
        for index in range(self.notebook.GetPageCount()):
            if self.notebook.GetPageText(index) == name:
                self.notebook.SetSelection(index)
                self.notebook.Update()
                break

    def _on_gloss(self, _event):
        self._show_action_tab("Gloss")
        names = self.centering_net_panel.get_selected_nets()
        if not names:
            return
        if self._on_gloss_callback is None:
            self.EndModal(wx.ID_OK)
            return
        self.gloss_button.Disable()
        self.centering_button.Disable()
        try:
            completed = self._on_gloss_callback(
                self.values(), names, self.append_log)
            if completed:
                self._show_action_tab("Log")
        finally:
            self.gloss_button.Enable()
            self.centering_button.Enable()

    def _on_centering(self, _event):
        self._show_action_tab("Centering")
        selected_nets = self.centering_net_panel.get_selected_nets()
        if not selected_nets:
            wx.MessageBox(
                "Select at least one modifiable net.",
                "Centering", wx.OK | wx.ICON_INFORMATION)
            return
        if self._on_centering_callback is None:
            return
        self.centering_button.Disable()
        self.gloss_button.Disable()
        try:
            result = self._on_centering_callback(
                self.values(), selected_nets, self.append_log)
            if isinstance(result, dict):
                doors = int(result.get("doors_centered", 0))
                proximity = float(result.get(
                    "centering_proximity_mm",
                    self.centering_proximity_mm.GetValue()))
                if doors:
                    self.centering_status.SetLabel(
                        f"{doors} door(s) centered at Proxi {proximity:.2f} mm.")
                else:
                    self.centering_status.SetLabel(
                        "No eligible door for the selected nets at "
                        f"Proxi {proximity:.2f} mm.")
                cleanup_saved = float(result.get("cleanup_saved_mm", 0.0))
                if cleanup_saved > 0:
                    self.centering_status.SetLabel(
                        self.centering_status.GetLabel() +
                        f" Cleanup: {cleanup_saved:.4f} mm saved.")
            elif result is False:
                self.centering_status.SetLabel(
                    "Centering failed; see the Log tab.")
        finally:
            self.gloss_button.Enable()
            self.centering_button.Enable()

    def append_log(self, text):
        self.log_text.AppendText(str(text))
        self.log_text.ShowPosition(self.log_text.GetLastPosition())

    def log_value(self):
        return self.log_text.GetValue()

    @staticmethod
    def _krt_version():
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = (
            os.path.join(plugin_dir, "KRT", "VERSION"),
            os.path.join(os.path.dirname(plugin_dir), "KRT", "VERSION"),
        )
        for version_file in candidates:
            try:
                with open(version_file, encoding="utf-8") as source:
                    return source.read().strip()
            except OSError:
                pass
        return "Unknown"

    def values(self):
        return {key: control.GetValue()
                for key, control in self.controls.items()} | {
                    "grid_step": self.grid_step.GetValue(),
                    "budget_seconds": self.budget_seconds.GetValue(),
                    "g4_max_passes": self.g4_max_passes.GetValue(),
                    "centering_proximity_mm": (
                        self.centering_proximity_mm.GetValue()),
                }
