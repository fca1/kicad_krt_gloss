"""Exercise the distributed plugin on a synthetic board using real macOS KiCad."""
import importlib
import json
from pathlib import Path
import platform
import sys
import time
import zipfile

import pcbnew
import wx

archive, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    package.extractall(output / "package")
sys.path.insert(0, str(output / "package"))
app = wx.App(False)
plugin = importlib.import_module("plugins")  # Runs real ActionPlugin registration.
from plugins.runtime import configure_krt_runtime
configure_krt_runtime()
import grid_router
from plugins.settings_dialog import GlossSettingsDialog, DEFAULTS
from plugins.board_adapter import build_krt_config, apply_gloss, _refill_and_rebuild
from kicad_parser import build_pcb_data_from_board
from dgloss import GlossConfig, run_final_gloss

print("ENVIRONMENT", sys.version, platform.machine(), pcbnew.GetBuildVersion(), flush=True)
print("RUST", grid_router.__file__, flush=True)
assert str(output / "package") in plugin.__file__
assert pcbnew.GetBuildVersion().startswith("10.0")
dialog = GlossSettingsDialog(None, dict(DEFAULTS), 0)
assert dialog.values()["budget_seconds"] == 20.0
dialog.Destroy()
app.ProcessPendingEvents()
print("PASS: plugin registration and dialog construction", flush=True)

board = pcbnew.BOARD()
net = pcbnew.NETINFO_ITEM(board, "SMOKE")
board.Add(net)
def point(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
for index, xy in enumerate(((4, 4), (12, 8)), 1):
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetReference(f"J{index}")
    board.Add(footprint)
    pad = pcbnew.PAD(footprint)
    pad.SetNumber("1")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(point(1.5, 1.5))
    pad.SetDrillSize(point(0.7, 0.7))
    pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    pad.SetPosition(point(*xy))
    pad.SetNetCode(net.GetNetCode())
    footprint.Add(pad)
for a, b in zip(((4, 4), (8, 4), (8, 8)), ((8, 4), (8, 8), (12, 8))):
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(point(*a)); track.SetEnd(point(*b))
    track.SetWidth(pcbnew.FromMM(0.25)); track.SetLayer(pcbnew.F_Cu)
    track.SetNetCode(net.GetNetCode()); board.Add(track)
for a, b in zip(((0, 0), (20, 0), (20, 15), (0, 15)),
                ((20, 0), (20, 15), (0, 15), (0, 0))):
    edge = pcbnew.PCB_SHAPE(board)
    edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetLayer(pcbnew.Edge_Cuts)
    edge.SetStart(point(*a)); edge.SetEnd(point(*b))
    edge.SetWidth(pcbnew.FromMM(0.05)); board.Add(edge)
zone = pcbnew.ZONE(board)
zone.SetLayer(pcbnew.B_Cu); zone.SetNetCode(net.GetNetCode())
zone.SetLocalClearance(pcbnew.FromMM(0.2))
zone.SetMinThickness(pcbnew.FromMM(0.2))
outline = zone.Outline(); outline.NewOutline()
for x, y in ((1, 1), (19, 1), (19, 14), (1, 14)):
    outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
board.Add(zone)
_refill_and_rebuild(board, pcbnew)
board.SetFileName(str(output / "before.kicad_pcb"))
assert pcbnew.SaveBoard(board.GetFileName(), board)
before = sum(t.GetLength() for t in board.GetTracks()) / 1e6
data = build_pcb_data_from_board(board)
config = build_krt_config(board, data, 0.1, net_ids=[net.GetNetCode()])
results = []
started = time.perf_counter()
outcome = run_final_gloss(results, data, config,
    GlossConfig(enable_multipasses=False), net_ids=[net.GetNetCode()])
applied = apply_gloss(board, results, outcome)
after = sum(t.GetLength() for t in board.GetTracks()) / 1e6
assert after < before, (before, after)
assert all(t.GetNetCode() == net.GetNetCode() for t in board.GetTracks())
assert zone.IsFilled()
assert pcbnew.SaveBoard(str(output / "after.kicad_pcb"), board)
reloaded = pcbnew.LoadBoard(str(output / "after.kicad_pcb"))
assert reloaded is not None
assert len(list(reloaded.GetTracks())) == len(list(board.GetTracks()))
summary = dict(architecture=platform.machine(), kicad=pcbnew.GetBuildVersion(),
    before_mm=before, after_mm=after, elapsed_seconds=time.perf_counter()-started,
    applied=applied, status="passed", limitations="Automated smoke test, not manual GUI acceptance or full DRC")
(output / "summary.json").write_text(json.dumps(summary, indent=2))
print("PASS", json.dumps(summary), flush=True)
