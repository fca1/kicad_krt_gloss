"""UI-thread polling of a detached Gloss session; no native calls in workers."""

import wx


class GlossProgressDialog(wx.Dialog):
    def __init__(self, parent, session):
        super().__init__(parent, title="Track Gloss", size=(440, 180))
        self.session = session
        self.label = wx.StaticText(self, label="Gloss calculation in progress…")
        self.gauge = wx.Gauge(self, range=100)
        self.pause_button = wx.Button(self, label="Pause")
        self.cancel_button = wx.Button(self, label="Cancel")
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self.label, 0, wx.ALL | wx.EXPAND, 12)
        box.Add(self.gauge, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 12)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self.pause_button, 0, wx.ALL, 8)
        buttons.Add(self.cancel_button, 0, wx.ALL, 8)
        box.Add(buttons, 0, wx.ALIGN_RIGHT)
        self.SetSizer(box)
        self.pause_button.Bind(wx.EVT_BUTTON, self._pause)
        self.cancel_button.Bind(wx.EVT_BUTTON, self._cancel)
        self.Bind(wx.EVT_CLOSE, self._cancel)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._poll, self.timer)
        self.timer.Start(100)

    def _pause(self, event):
        control = self.session.control
        if control.pause_requested:
            control.resume()
            self.pause_button.SetLabel("Pause")
            self.label.SetLabel("Gloss calculation in progress…")
        else:
            control.pause()
            self.pause_button.SetLabel("Resume")
            self.label.SetLabel("Pausing after the current check…")

    def _cancel(self, event):
        self.session.control.cancel()
        self.pause_button.Disable()
        self.cancel_button.Disable()
        self.label.SetLabel("Cancelling; the board will remain unchanged…")
        if isinstance(event, wx.CloseEvent) and event.CanVeto():
            event.Veto()

    def _poll(self, event):
        if self.session.done.is_set():
            self.timer.Stop()
            self.EndModal(wx.ID_OK)
        elif self.session.control.paused:
            self.label.SetLabel("Paused — Resume continues the same search.")
        else:
            self.gauge.Pulse()
