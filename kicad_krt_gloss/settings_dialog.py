"""Small standalone configuration dialog; no routing controls are duplicated."""

import wx


DEFAULTS = {
    "enable_g3_1": True,
    "enable_g3_2": True,
    "enable_g3_3": True,
    "enable_g3_4": True,
    "grid_step": 0.1,
}


class GlossSettingsDialog(wx.Dialog):
    def __init__(self, parent, values, selected_count):
        super().__init__(parent, title="KiCad KRT Gloss")
        values = dict(DEFAULTS, **(values or {}))
        panel = wx.Panel(self)
        content = wx.BoxSizer(wx.VERTICAL)
        scope = (f"{selected_count} selected net(s) will be glossed completely."
                 if selected_count else
                 "No net selected: all routed nets will be glossed.")
        content.Add(wx.StaticText(panel, label=scope), 0, wx.ALL, 10)

        self.controls = {}
        labels = {
            "enable_g3_1": "G3.1 — mobile vias",
            "enable_g3_2": "G3.2 — pad terminals",
            "enable_g3_3": "G3.3 — sliding T nodes",
            "enable_g3_4": "G3.4 — complete via chains",
        }
        for key, label in labels.items():
            control = wx.CheckBox(panel, label=label)
            control.SetValue(bool(values[key]))
            self.controls[key] = control
            content.Add(control, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(panel, label="KRT grid step (mm):"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.grid_step = wx.SpinCtrlDouble(
            panel, min=0.01, max=2.0, initial=float(values["grid_step"]),
            inc=0.01)
        self.grid_step.SetDigits(3)
        row.Add(self.grid_step, 1)
        content.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        content.Add(wx.StaticText(
            panel,
            label=("0.1 mm is KRT's default. For a direct KRT API call, "
                   "the actual KRT grid is used instead.")),
                  0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(content)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())

    def values(self):
        return {key: control.GetValue()
                for key, control in self.controls.items()} | {
                    "grid_step": self.grid_step.GetValue()}
