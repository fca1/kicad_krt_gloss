"""KiCad IPC plugin entry point; deliberately never registers a SWIG action."""
import importlib
import os
from pathlib import Path
import sys
import types


def main():
    import wx
    from kipy import KiCad
    app = wx.App(False)
    bridge = None
    try:
        if not os.environ.get('KICAD_API_SOCKET'):
            raise RuntimeError('Launch Gloss from the KiCad IPC toolbar (no instance socket supplied).')
        os.environ['KRG_IPC'] = '1'
        package = types.ModuleType('_krg_ipc')
        package.__path__ = [str(Path(__file__).resolve().parent)]
        sys.modules[package.__name__] = package
        runtime = importlib.import_module('_krg_ipc.runtime')
        runtime.configure_krt_runtime()
        module = importlib.import_module('_krg_ipc.ipc_bridge')
        bridge = module.IpcBoardBridge(KiCad(timeout_ms=15000))
        action = importlib.import_module('_krg_ipc.action_plugin')
        action.KICAD = bridge
        branches = importlib.import_module('_krg_ipc.branch_selection_prototype')
        branches.activate(action)
        plugin = action.KiCadKrtGlossPlugin()
        plugin.__class__._last_log = 'IPC mode: branch selection is available; branch highlighting is unavailable.\n'
        plugin.Run()
        if plugin._settings_dialog is not None:
            app.MainLoop()
    except Exception as exc:
        wx.MessageBox(str(exc), 'KiCad KRT Gloss — IPC', wx.OK | wx.ICON_ERROR)
        return 1
    finally:
        if bridge is not None:
            bridge.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
