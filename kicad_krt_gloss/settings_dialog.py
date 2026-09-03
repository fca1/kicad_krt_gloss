"""Small standalone configuration dialog; no routing controls are duplicated."""

import os
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
}


class GlossSettingsDialog(wx.Dialog):
    def __init__(self, parent, values, selected_count,
                 selected_branch_count=0, *, on_gloss=None, initial_log=""):
        super().__init__(parent, title="KiCad KRT Gloss")
        values = dict(DEFAULTS, **(values or {}))
        self._on_gloss_callback = on_gloss
        self.notebook = wx.Notebook(self)
        panel = wx.Panel(self.notebook)
        content = wx.BoxSizer(wx.VERTICAL)
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
            if key == "selection_uses_elementary_branches":
                scope = (f"Selected nets: {selected_count}"
                         if selected_count else
                         "Selected nets: 0 (all routed nets)")
                content.Add(wx.StaticText(panel, label=scope), 0,
                            wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
                content.Add(wx.StaticText(
                    panel, label=f"Selected elementary branches: "
                                 f"{selected_branch_count}"), 0,
                    wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

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
        panel.SetSizer(content)
        self.notebook.AddPage(panel, "General")

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
        clear_log = wx.Button(log_panel, label="Clear Log")
        clear_log.SetToolTip("Clear all Track Gloss log output.")
        clear_log.Bind(wx.EVT_BUTTON, self._on_clear_log)
        log_content.Add(clear_log, 0,
                        wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 5)
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
        for label, value in (
                ("KRG version:", __version__),
                ("KRT version:", self._krt_version()),
                ("Author:", "Frantz"),
                ("Co-author:", "ChatGPT/Codex (OpenAI)"),
                ("KRT author:", "DrAndyHaas")):
            name = wx.StaticText(about, label=label)
            name.SetFont(name.GetFont().Bold())
            info.Add(name, 0, wx.ALIGN_RIGHT)
            info.Add(wx.StaticText(about, label=value), 0, wx.ALIGN_LEFT)
        about_content.Add(info, 0, wx.ALIGN_CENTER | wx.ALL, 12)
        about_content.Add(wx.adv.HyperlinkCtrl(
            about, label="KRG GitHub Repository",
            url="https://github.com/fca1/kicad_krt_gloss"),
            0, wx.ALIGN_CENTER | wx.TOP | wx.LEFT | wx.RIGHT, 8)
        about_content.Add(wx.adv.HyperlinkCtrl(
            about, label="KRT GitHub Repository",
            url="https://github.com/drandyhaas/KiCadRoutingTools"),
            0, wx.ALIGN_CENTER | wx.ALL, 8)
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

    def _on_clear_log(self, _event):
        self.log_text.Clear()

    def _on_gloss(self, _event):
        if self._on_gloss_callback is None:
            self.EndModal(wx.ID_OK)
            return
        self.gloss_button.Disable()
        try:
            self._on_gloss_callback(self.values(), self.append_log)
        finally:
            self.gloss_button.Enable()
            self.notebook.SetSelection(1)

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
                    "grid_step": self.grid_step.GetValue()}
