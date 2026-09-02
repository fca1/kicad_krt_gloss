"""Small standalone configuration dialog; no routing controls are duplicated."""

import os
import wx
import wx.adv

from .version import __version__


DEFAULTS = {
    "enable_g3_1": True,
    "enable_g3_2": True,
    "enable_g3_3": True,
    "enable_g3_4": True,
    "enable_noncollinear_t_rails": True,
    "enable_multipasses": True,
    "grid_step": 0.1,
}


class GlossSettingsDialog(wx.Dialog):
    def __init__(self, parent, values, selected_count):
        super().__init__(parent, title="KiCad KRT Gloss")
        values = dict(DEFAULTS, **(values or {}))
        notebook = wx.Notebook(self)
        panel = wx.Panel(notebook)
        content = wx.BoxSizer(wx.VERTICAL)
        scope = (f"{selected_count} selected net(s) will be glossed completely."
                 if selected_count else
                 "No net is selected: all routed nets will be glossed.")
        content.Add(wx.StaticText(panel, label=scope), 0, wx.ALL, 10)

        self.controls = {}
        labels = {
            "enable_g3_1": "G3.1 — mobile vias",
            "enable_g3_2": "G3.2 — pad terminals",
            "enable_g3_3": "G3.3 — sliding T nodes",
            "enable_noncollinear_t_rails": (
                "G3.3 — allow non-collinear rails"),
            "enable_g3_4": "G3.4 — complete via chains",
            "enable_multipasses": "G4 — multi-net convergence passes",
        }
        tooltips = {
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
        panel.SetSizer(content)
        notebook.AddPage(panel, "General")

        about = wx.Panel(notebook)
        about_content = wx.BoxSizer(wx.VERTICAL)
        about_content.AddSpacer(16)
        icon_path = os.path.join(os.path.dirname(__file__), "icon_64.png")
        if os.path.exists(icon_path):
            bitmap = wx.StaticBitmap(about, bitmap=wx.Bitmap(icon_path))
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
            about, label="GitHub Repository",
            url="https://github.com/fca1/kicad_krt_gloss"),
            0, wx.ALIGN_CENTER | wx.ALL, 8)
        license_text = wx.StaticText(about, label="Open source — MIT License")
        license_text.SetForegroundColour(wx.Colour(128, 128, 128))
        about_content.Add(license_text, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        about_content.AddStretchSpacer()
        about.SetSizer(about_content)
        notebook.AddPage(about, "About")

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(notebook, 1, wx.EXPAND)
        buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())

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
