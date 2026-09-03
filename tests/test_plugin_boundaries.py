"""Architecture tests that need neither KiCad nor pcbnew."""

from pathlib import Path
import importlib.util
import shutil
import sys
import types
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kicad_krt_gloss.selection import (
    native_arc_net_ids, selected_net_ids, selected_seed_segments)
from kicad_krt_gloss.board_adapter import (
    _krt_via_key, _native_segment_key, _native_via_key, _segment_key,
    build_krt_config)
from kicad_krt_gloss import runtime


class Item:
    def __init__(self, net_id=0, selected=True):
        self.net_id = net_id
        self.selected = selected

    def GetNetCode(self):
        return self.net_id

    def IsSelected(self):
        return self.selected

    def GetClass(self):
        return "PCB_TRACK"


class Footprint(Item):
    def __init__(self, pads, selected=False):
        super().__init__(0, selected)
        self.pads = pads

    def Pads(self):
        return self.pads


class Board:
    def __init__(self):
        self.tracks = [Item(7), Item(7), Item(8, False)]
        self.footprints = [Footprint([Item(9, False)], selected=True),
                           Footprint([Item(10)], selected=False)]
        self.zones = [Item(11), Item(0)]

    def GetTracks(self):
        return self.tracks

    def GetFootprints(self):
        return self.footprints

    def GetAreaCount(self):
        return len(self.zones)

    def GetArea(self, index):
        return self.zones[index]


def test_selection_filters_every_supported_item_to_unique_complete_net_ids():
    assert selected_net_ids(Board()) == [7, 9, 10, 11]


def test_selected_straight_track_maps_to_its_krt_segment_seed():
    class Point:
        def __init__(self, x, y): self.x, self.y = x, y

    class Track(Item):
        def GetStart(self): return Point(1.0, 2.0)
        def GetEnd(self): return Point(3.0, 4.0)
        def GetLayer(self): return 0
        def GetWidth(self): return 0.2

    track = Track(7)
    board = types.SimpleNamespace(
        GetTracks=lambda: [track], GetLayerName=lambda _layer: "F.Cu")
    segment = types.SimpleNamespace(
        start_x=3.0, start_y=4.0, end_x=1.0, end_y=2.0,
        layer="F.Cu", net_id=7, width=0.2, graphic=False)
    pcb_data = types.SimpleNamespace(segments=[segment])

    with patch.dict(sys.modules, {"pcbnew": types.SimpleNamespace(ToMM=float)}):
        assert selected_seed_segments(board, pcb_data) == [segment]


def test_native_arc_nets_are_excluded_at_the_plugin_boundary():
    straight = Item(7)
    arc = Item(8)
    arc.GetClass = lambda: "PCB_ARC"
    board = types.SimpleNamespace(GetTracks=lambda: [straight, arc])
    assert native_arc_net_ids(board) == [8]


def test_dgloss_runtime_does_not_depend_on_pcbnew_or_plugin_package():
    for source in (ROOT / "dgloss").glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "pcbnew" not in text, source.name
        assert "kicad_krt_gloss" not in text, source.name


def test_packaged_runtime_exposes_its_embedded_dgloss(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "installed_plugin"
    plugin_dir.mkdir()
    shutil.copy2(ROOT / "kicad_krt_gloss" / "runtime.py",
                 plugin_dir / "runtime.py")
    (plugin_dir / "dgloss").mkdir()
    (plugin_dir / "dgloss" / "__init__.py").write_text(
        "PACKAGED_MARKER = True\n", encoding="utf-8")
    for directory in (plugin_dir / "KRT" / "py_router",
                      plugin_dir / "KRT" / "rust_router"):
        directory.mkdir(parents=True)

    spec = importlib.util.spec_from_file_location(
        "packaged_krg_runtime", plugin_dir / "runtime.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    monkeypatch.setattr(runtime, "_resolve_rust_binary", lambda root: None)
    old_path = list(sys.path)
    sys.modules.pop("dgloss", None)
    try:
        runtime.configure_krt_runtime()
        import dgloss
        assert dgloss.PACKAGED_MARKER is True
    finally:
        sys.modules.pop("dgloss", None)
        sys.path[:] = old_path


def test_dialog_has_a_top_level_sizer_for_panel_and_buttons():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert "panel.SetSizer(content)" in source
    assert 'self.notebook.AddPage(panel, "General")' in source
    assert 'self.notebook.AddPage(log_panel, "Log")' in source
    assert 'self.notebook.AddPage(about, "About")' in source
    assert "outer.Add(self.notebook, 1, wx.EXPAND)" in source
    assert "self.SetSizerAndFit(outer)" in source


def test_dialog_keeps_a_post_run_log_with_krt_style_controls():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert 'label="Clear Log"' in source
    assert 'label="Gloss"' in source
    assert 'label="Close"' in source
    assert "wx.TE_READONLY" in source
    assert "self.notebook.SetSelection(1)" in source

    action = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert '_last_log = ""' in action
    assert "initial_log=self.__class__._last_log" in action
    assert 'print("\\n=== Track Gloss result ===")' in action


def test_about_tab_uses_project_versions_and_attribution():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert '("KRG version:", __version__, None)' in source
    assert '("KRT version:", self._krt_version(), None)' in source
    assert '("Author:", "Frantz",' in source
    assert '("Co-author:", "ChatGPT/Codex (OpenAI)", None)' in source
    assert '("KRT author:", "DrAndyHaas",' in source
    assert 'label="GitHub Repository"' in source
    assert '"https://github.com/fca1/kicad_krt_gloss"' in source
    assert '"https://github.com/drandyhaas/KiCadRoutingTools"' in source
    assert "info.AddSpacer(10)" in source
    assert "info.AddSpacer((1, 10))" not in source
    assert 'selection_value = str(selected_count) if selected_count else "ALL"' \
        in source


def test_pcm_package_includes_the_about_logo():
    source = (ROOT / "package_pcm.py").read_text(encoding="utf-8")
    assert '"icon_24.png", "icon_64.png"' in source


def test_dialog_exposes_the_integrated_gloss_options_by_public_name():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert '\"enable_noncollinear_t_rails\": True' in source
    assert '\"enable_multipasses\": True' in source
    assert "enable_g4" not in source
    assert source.count("SetToolTip(") >= 2
    assert "Repeat enabled optimizations" in source
    assert "KRT defaults to 0.1 mm" not in source
    assert "For a direct KRT API call" not in source


def test_settings_dialog_is_shown_unless_exactly_one_net_is_selected():
    source = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert "values = dict(self.__class__._settings)" in source
    assert "if len(net_ids) != 1:" in source
    assert source.index("if len(net_ids) != 1:") < source.index(
        "dialog = GlossSettingsDialog")


def test_plugin_selection_mode_defaults_to_be_and_cli_stays_net_only():
    dialog = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    action = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    cli = (ROOT / "gloss.py").read_text(encoding="utf-8")
    key = '"selection_uses_elementary_branches"'
    assert dialog.index(f"{key}: True") < dialog.index('"enable_g3_1": True')
    assert "Selected elementary branches:" not in dialog
    assert 'content.Add(selected_net, 0, wx.ALIGN_RIGHT' in dialog
    assert "stopping at a pad, free end, or T/X" in dialog
    assert key in action
    assert key not in cli


def test_runtime_log_messages_are_english_only():
    sources = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in ("dgloss/pipeline.py", "dgloss/passes.py",
                         "dgloss/stats.py", "kicad_krt_gloss/action_plugin.py",
                         "gloss.py"))
    french_log_terms = (
        "améliorés", "déplacés", "optimisés", "sans rail colinéaire",
        "coudes", "affinés", "supprimés", "désactivé", "expiré",
        "parcourus", "certifiés", "transformations multinet",
    )
    assert not any(term in sources for term in french_log_terms)


def test_single_selected_net_skips_the_success_summary_dialog():
    source = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert "if len(net_ids) != 1:" in source
    assert source.index("if len(net_ids) != 1:") < source.index(
        'f"Scope: {scope}\\n"')
    assert "f'Differences are shown on {debug_layer} '" in source
    assert '("TrackGloss Changes").' in source


def test_cli_exposes_optional_auto_or_explicit_debug_layer():
    source = (ROOT / "gloss.py").read_text(encoding="utf-8")
    assert '"--debug-layer"' in source
    assert 'choices=("auto",)' in source
    assert 'write_cli_debug_overlay(' in source


def test_plugin_renders_the_complete_final_delta_once():
    source = (ROOT / "kicad_krt_gloss" / "board_adapter.py").read_text(
        encoding="utf-8")
    assert 'add_changes_to_board(board, outcome.visual_changes, stage="G4")' in source
    assert "changes_by_stage" not in source
    assert "debug overlay skipped" in source


def test_plugin_config_delegates_dru_rules_to_krt():
    class NetClass:
        def GetTrackWidth(self): return 0.2
        def GetClearance(self): return 0.1
        def GetViaDiameter(self): return 0.4
        def GetViaDrill(self): return 0.2

    class NetSettings:
        def GetDefaultNetclass(self): return NetClass()
        def GetEffectiveNetClass(self, _name): return NetClass()

    class Settings:
        m_NetSettings = NetSettings()
        m_CopperEdgeClearance = 0.15

    class LiveBoard:
        def GetDesignSettings(self): return Settings()
        def GetFileName(self): return "example.kicad_pcb"

    pcb = types.SimpleNamespace(
        board_info=types.SimpleNamespace(copper_layers=["F.Cu", "B.Cu"]),
        nets={1: types.SimpleNamespace(name="N1")},
        source_path="example.kicad_pcb")
    pcbnew = types.SimpleNamespace(ToMM=float)
    with (patch.dict(sys.modules, {"pcbnew": pcbnew}),
          patch("kicad_dru.install_layer_clearances") as install_layers,
          patch("kicad_dru.install_track_clearances") as install_tracks):
        config = build_krt_config(LiveBoard(), pcb, 0.1, net_ids=[1])
    install_layers.assert_called_once_with(
        config, None, "example.kicad_pcb", pcb)
    install_tracks.assert_called_once_with(
        config, None, "example.kicad_pcb", pcb, routed_net_ids=[1])


def test_native_keys_distinguish_width_and_via_geometry():
    pcbnew = types.SimpleNamespace(ToMM=float)
    board = types.SimpleNamespace(GetLayerName=lambda layer: layer)

    class Track:
        def __init__(self, width): self.width = width
        def GetStart(self): return types.SimpleNamespace(x=1.0, y=2.0)
        def GetEnd(self): return types.SimpleNamespace(x=3.0, y=4.0)
        def GetLayer(self): return "F.Cu"
        def GetNetCode(self): return 7
        def GetWidth(self): return self.width

    first = types.SimpleNamespace(
        start_x=1.0, start_y=2.0, end_x=3.0, end_y=4.0,
        layer="F.Cu", net_id=7, width=0.2)
    second = types.SimpleNamespace(**vars(first))
    second.width = 0.3
    assert _segment_key(first) != _segment_key(second)
    assert (_native_segment_key(board, pcbnew, Track(0.2)) !=
            _native_segment_key(board, pcbnew, Track(0.3)))

    class NativeVia:
        def GetPosition(self): return types.SimpleNamespace(x=5.0, y=6.0)
        def GetNetCode(self): return 7
        def GetWidth(self): return 0.4
        def GetDrillValue(self): return 0.2
        def TopLayer(self): return "F.Cu"
        def BottomLayer(self): return "B.Cu"

    via = types.SimpleNamespace(
        x=5.0, y=6.0, net_id=7, size=0.4, drill=0.2,
        layers=["F.Cu", "B.Cu"])
    assert _native_via_key(board, pcbnew, NativeVia()) == _krt_via_key(via)


def test_rust_binary_resolution_keeps_krt_submodule_immutable(
        tmp_path, monkeypatch):
    root = tmp_path / "KRT"
    rust = root / "rust_router"
    rust.mkdir(parents=True)
    source = rust / "grid_router-windows-x86_64.pyd"
    source.write_bytes(b"test-binary")
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")

    resolved = runtime._resolve_rust_binary(root)

    assert resolved.read_bytes() == b"test-binary"
    assert resolved.parent != rust
    assert not (rust / "grid_router.pyd").exists()
