"""Standalone Gloss settings and independent Centering action."""

import os
from types import SimpleNamespace
import wx
import wx.adv

from .version import __version__


DEFAULTS = {
    "selection_uses_elementary_branches": True,
    "enable_g3_1": True,
    "enable_g3_2": True,
    "enable_g3_3": True,
    "enable_g3_4": True,
    "enable_noncollinear_t_rails": True,
    "enable_multipasses": True,
    "grid_step": 0.1,
    "budget_seconds": 20.0,
    "centering_proximity_mm": 1.0,
    "centering_build_multi_door_path": True,
    "centering_build_new_segments": True,
}


class GlossSettingsDialog(wx.Dialog):
    def __init__(self, parent, values, selected_count, *, on_gloss=None,
                 on_centering=None, pcb_data=None, centering_nets=(),
                 preselected_centering_nets=(), initial_log=""):
        super().__init__(parent, title="KiCad KRT Gloss")
        values = dict(DEFAULTS, **(values or {}))
        self._on_gloss_callback = on_gloss
        self._on_centering_callback = on_centering
        self.notebook = wx.Notebook(self)
        panel = wx.Panel(self.notebook)
        content = wx.BoxSizer(wx.VERTICAL)
        selection_label = "Selected Net" if selected_count <= 1 else \
            "Selected Nets"
        selection_value = str(selected_count) if selected_count else "ALL"
        selected_net = wx.StaticText(
            panel, label=f"{selection_label}: {selection_value}")
        selected_font = selected_net.GetFont()
        selected_font.SetPointSize(selected_font.GetPointSize() + 4)
        selected_font.SetWeight(wx.FONTWEIGHT_BOLD)
        selected_net.SetFont(selected_font)
        content.Add(selected_net, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.controls = {}
        labels = {
            "selection_uses_elementary_branches": (
                "Selection — use elementary branches"),
            "enable_g3_1": "G3.1 — mobile vias",
            "enable_g3_2": "G3.2 — pad terminals",
            "enable_g3_3": "G3.3 — sliding T nodes",
            "enable_noncollinear_t_rails": (
                "G3.3 — allow non-collinear rails"),
            "enable_g3_4": "G3.4 — complete via chains",
            "enable_multipasses": "G4 — multi-net convergence passes",
        }
        tooltips = {
            "selection_uses_elementary_branches": (
                "On: each selected straight track seeds its maximal "
                "elementary branch, stopping at a pad, free end, or T/X "
                "junction. Off: every complete net identified by the "
                "selection is glossed."),
            "enable_g3_1": (
                "Move eligible vias on the KRT grid to shorten their tracks."),
            "enable_g3_2": (
                "Shorten track approaches to pads while preserving connectivity."),
            "enable_g3_3": (
                "Slide T-junction branches along existing track rails."),
            "enable_noncollinear_t_rails": (
                "Also use each branch of a non-collinear T-junction as a rail."),
            "enable_g3_4": (
                "Optimize the complete track chains connected through movable vias."),
            "enable_multipasses": (
                "Repeat enabled optimizations across nets until convergence or timeout."),
        }
        for key, label in labels.items():
            control = wx.CheckBox(panel, label=label)
            control.SetValue(bool(values[key]))
            control.SetToolTip(tooltips[key])
            self.controls[key] = control
            content.Add(control, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(panel, label="KRT grid step (mm):"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.grid_step = wx.SpinCtrlDouble(
            panel, min=0.01, max=2.0, initial=float(values["grid_step"]),
            inc=0.01)
        self.grid_step.SetDigits(3)
        self.grid_step.SetToolTip(
            "Grid resolution used by standalone gloss.")
        row.Add(self.grid_step, 1)
        content.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        budget_row = wx.BoxSizer(wx.HORIZONTAL)
        budget_row.Add(wx.StaticText(panel, label="Gloss time budget (s):"),
                       0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.budget_seconds = wx.SpinCtrlDouble(
            panel, min=10.0, max=240.0,
            initial=float(values["budget_seconds"]), inc=10.0)
        self.budget_seconds.SetDigits(0)
        self.budget_seconds.SetToolTip(
            "Cooperative dgloss optimization budget. Total runtime may be "
            "longer because final KRT smooth, certification, and KiCad apply "
            "run outside this strict limit.")
        budget_row.Add(self.budget_seconds, 1)
        content.Add(budget_row, 0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(content)
        self.notebook.AddPage(panel, "General")

        self._create_centering_tab(
            pcb_data, centering_nets, preselected_centering_nets, values)

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
        close_button = wx.Button(self, label="Close")
        close_button.SetToolTip("Close this dialog.")
        close_button.Bind(wx.EVT_BUTTON,
                          lambda _event: self.EndModal(wx.ID_CANCEL))
        buttons.Add(self.gloss_button, 1, wx.RIGHT, 5)
        buttons.Add(close_button, 1)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())

    def _create_centering_tab(self, pcb_data, centering_nets,
                              preselected_nets, values):
        """Build the special G3.6 page around KRT's net-selection panel."""
        panel = wx.Panel(self.notebook)
        content = wx.BoxSizer(wx.VERTICAL)
        columns = wx.BoxSizer(wx.HORIZONTAL)

        net_box = wx.StaticBox(panel, label="Net Selection")
        net_sizer = wx.StaticBoxSizer(net_box, wx.VERTICAL)
        from kicad_routing_plugin.fanout_gui import NetSelectionPanel
        if pcb_data is None:
            pcb_data = SimpleNamespace(nets={}, pads_by_net={}, footprints={})
        self.centering_net_panel = NetSelectionPanel(
            panel, pcb_data,
            instructions="Select modifiable nets to center...",
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
        columns.Add(net_sizer, 2, wx.EXPAND | wx.ALL, 8)

        options = wx.BoxSizer(wx.VERTICAL)
        icon_path = os.path.join(
            os.path.dirname(__file__), "centering_illustration.png")
        if os.path.exists(icon_path):
            image = wx.Image(icon_path, wx.BITMAP_TYPE_PNG)
            options.Add(wx.StaticBitmap(panel, bitmap=wx.Bitmap(image)), 0,
                        wx.ALIGN_CENTER | wx.ALL, 10)

        parameters_box = wx.StaticBox(panel, label="Centering Parameters")
        parameters = wx.StaticBoxSizer(parameters_box, wx.VERTICAL)
        proximity_row = wx.BoxSizer(wx.HORIZONTAL)
        proximity_row.Add(wx.StaticText(panel, label="Proxi (mm):"), 0,
                          wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.centering_proximity_mm = wx.SpinCtrlDouble(
            panel, min=0.0, max=5.0,
            initial=float(values["centering_proximity_mm"]), inc=0.1)
        self.centering_proximity_mm.SetDigits(2)
        self.centering_proximity_mm.SetToolTip(
            "Maximum absolute proximity to obstacles, in millimetres.")
        proximity_row.Add(self.centering_proximity_mm, 1)
        parameters.Add(proximity_row, 0, wx.EXPAND | wx.ALL, 8)

        self.centering_build_multi_door_path = wx.CheckBox(
            panel, label="Build multi-door path")
        self.centering_build_multi_door_path.SetValue(bool(
            values["centering_build_multi_door_path"]))
        self.centering_build_multi_door_path.SetToolTip(
            "Allow one transformation to center a branch across several doors.")
        parameters.Add(self.centering_build_multi_door_path, 0,
                       wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.centering_build_new_segments = wx.CheckBox(
            panel, label="Build new segments")
        self.centering_build_new_segments.SetValue(bool(
            values["centering_build_new_segments"]))
        self.centering_build_new_segments.SetToolTip(
            "Allow centering to increase the number of track segments.")
        parameters.Add(self.centering_build_new_segments, 0,
                       wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        options.Add(parameters, 0, wx.EXPAND | wx.ALL, 8)
        options.AddStretchSpacer()
        columns.Add(options, 1, wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM, 8)
        content.Add(columns, 1, wx.EXPAND)

        self.centering_button = wx.Button(panel, label="Centering")
        self.centering_button.SetToolTip(
            "Run only the G3.6 centering action on the checked nets.")
        self.centering_button.Bind(wx.EVT_BUTTON, self._on_centering)
        content.Add(self.centering_button, 0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.centering_status = wx.StaticText(panel, label="Ready.")
        content.Add(self.centering_status, 0,
                    wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(content)
        self.notebook.AddPage(panel, "Centering")

    def _on_clear_log(self, _event):
        self.log_text.Clear()

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

    def _on_gloss(self, _event):
        if self._on_gloss_callback is None:
            self.EndModal(wx.ID_OK)
            return
        self.gloss_button.Disable()
        try:
            self._on_gloss_callback(self.values(), self.append_log)
        finally:
            self.gloss_button.Enable()
            for index in range(self.notebook.GetPageCount()):
                if self.notebook.GetPageText(index) == "Log":
                    self.notebook.SetSelection(index)
                    break

    def _on_centering(self, _event):
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
                    "centering_proximity_mm": (
                        self.centering_proximity_mm.GetValue()),
                    "centering_build_multi_door_path": (
                        self.centering_build_multi_door_path.GetValue()),
                    "centering_build_new_segments": (
                        self.centering_build_new_segments.GetValue()),
                }
