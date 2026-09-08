"""Manual live-editor probe; never imported or packaged by the plugin.

With the KRG settings dialog open, run in KiCad's scripting console:
    runpy.run_path('/absolute/path/tools/probe_net_highlight.py')['start']('/C')

The timer only simulates a list click. Console results check painter input
flags on the live board; visible contrast still needs observation in KiCad.
No geometry, checked scope or board file is changed.
"""


def start(net_name=None, delay_ms=1500):
    import pcbnew
    import wx

    board = pcbnew.GetBoard()
    if board is None:
        raise RuntimeError('Run this probe inside the PCB editor.')
    dialog = next((window for window in wx.GetTopLevelWindows()
                   if hasattr(window, 'centering_net_panel') and window.IsShown()), None)
    if dialog is None:
        raise RuntimeError('Open the KRG settings dialog first.')

    def click():
        if not dialog or not dialog.IsShown():
            return
        control = dialog.centering_net_panel.net_list
        index = 0 if net_name is None else control.FindString(net_name)
        if index == wx.NOT_FOUND or not control.GetCount():
            print('Highlight probe: requested net is not visible in the list.')
            return
        name = control.GetString(index)
        for selected in control.GetSelections():
            control.Deselect(selected)
        control.SetSelection(index)
        event = wx.CommandEvent(wx.EVT_LISTBOX.typeId, control.GetId())
        event.SetEventObject(control)
        event.SetInt(index)
        event.SetString(name)
        control.GetEventHandler().ProcessEvent(event)
        tracks = [item for item in board.GetTracks() if item.GetNetname() == name]
        print('Highlight probe:', name, 'tracks/vias=', len(tracks),
              'brightened=', sum(item.IsBrightened() for item in tracks),
              '(painter input only; observe the PCB for visual confirmation)')

    return wx.CallLater(delay_ms, click)
