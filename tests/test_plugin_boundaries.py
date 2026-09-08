"""Architecture tests that need neither KiCad nor pcbnew."""

from pathlib import Path
import importlib.util
import ast
import json
import pytest
import shutil
import sys
import types
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kicad_krt_gloss.selection import (
    native_arc_net_ids, selected_net_ids, selected_pad_pair_distance_mm,
    selected_seed_segments)
from kicad_krt_gloss.board_adapter import (
    _krt_via_key, _native_segment_key, _native_via_key, _segment_key,
    _refill_and_rebuild, build_krt_config)
from kicad_krt_gloss.kicad_bridge import KiCadBoardBridge
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


def test_plugin_run_accepts_two_item_preparation_for_multiple_selected_nets():
    source = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    plugin = next(node for node in ast.parse(source).body
                  if isinstance(node, ast.ClassDef))
    run = next(node for node in plugin.body
               if isinstance(node, ast.FunctionDef) and node.name == "Run")
    for net_ids in ([], [1], [1, 2]):
        calls = []
        prepared = (types.SimpleNamespace(nets={
            i: types.SimpleNamespace(name=f'N{i}') for i in (1, 2, 3)}), [])
        settings = {"test": True}

        class Dialog:
            def __init__(self, parent, values, count, **kwargs):
                calls.append(("dialog", count))
                self.on_gloss = kwargs["on_gloss"]
                self.on_centering = kwargs["on_centering"]
                assert set(kwargs['preselected_centering_nets']) == (
                    {f'N{i}' for i in net_ids} if net_ids else {'N1', 'N2', 'N3'})

            def Bind(self, *_args): pass
            def Show(self):
                self.on_gloss(settings, ['N3'], lambda text: None)
                self.on_centering(settings, ['N3'], lambda text: None)
            def values(self): return settings
            def log_value(self): return ""
            def Destroy(self): pass

        class Plugin:
            _settings = settings
            _last_log = ""

            def _prepare_selection(self, board, parent):
                calls.append(("prepare",))
                return prepared

            def _modifiable_net_rows(self, board, pcb_data):
                calls.append(("modifiable",))
                return [('N1', 1), ('N2', 2), ('N3', 3)]

            def _prepare_checked_nets(self, board, parent, names):
                assert names == ['N3']
                calls.append(('fresh',))
                return prepared, [3]

            def _run_centering(self, board, parent, values, names, **kwargs):
                assert names == ['N3']
                assert kwargs['prepared'] is prepared
                calls.append(('centering',))

            def _run_gloss(self, board, parent, values, nets, **kwargs):
                calls.append(("run", nets, kwargs))

        kicad = types.SimpleNamespace(
            active_board=lambda: object(),
            selected_net_ids=lambda board: net_ids,
            selected_pad_pair_distance_mm=lambda board: None)
        namespace = {
            "wx": types.SimpleNamespace(GetTopLevelWindows=lambda: [],
                                        EVT_CLOSE=object()),
            "KICAD": kicad,
            "GlossSettingsDialog": Dialog,
        }
        exec(compile(ast.Module(body=[run], type_ignores=[]),
                     "action_plugin.Run", "exec"), namespace)
        namespace["Run"](Plugin())
        assert ("dialog", len(net_ids)) in calls if len(net_ids) != 1 else (
            not any(call[0] == "dialog" for call in calls))
        assert ("prepare",) in calls if len(net_ids) != 1 else (
            ("prepare",) not in calls)
        run_call = next(call for call in calls if call[0] == "run")
        assert run_call[1] == ([3] if len(net_ids) != 1 else net_ids)
        if len(net_ids) != 1:
            assert run_call[2].get("prepared") == prepared
            assert "show_progress" not in run_call[2]
            assert calls.count(('fresh',)) == 2
            assert ('centering',) in calls
        else:
            assert run_call[2] == {"show_progress": False}


def test_kicad_bridge_centralizes_native_board_and_selection_calls():
    calls = []
    native = types.SimpleNamespace(
        GetBoard=lambda: "live-board", Refresh=lambda: calls.append("refresh"))
    bridge = KiCadBoardBridge(native)
    bridge.selected_net_ids = lambda _board: [2]
    board = types.SimpleNamespace(GetNetsByNetcode=lambda: {
        1: types.SimpleNamespace(GetNetname=lambda: "N1"),
        2: types.SimpleNamespace(GetNetname=lambda: "N2")})

    assert bridge.active_board() == "live-board"
    assert bridge.selected_net_names(board) == {"N2"}
    bridge.refresh()
    assert calls == ["refresh"]


def test_action_plugin_routes_native_board_operations_through_bridge():
    source = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert "KICAD = KiCadBoardBridge()" in source
    assert "KICAD.active_board()" in source
    assert "KICAD.build_pcb_data(board)" in source
    assert "KICAD.apply_outcome(" in source
    assert source.count("KICAD.refresh()") == 2
    assert "pcbnew.GetBoard()" not in source
    assert "pcbnew.Refresh()" not in source


@pytest.mark.parametrize("has_zones, failure", [
    (False, None), (True, None), (True, "raise"), (True, "false")])
def test_zone_refill_precedes_connectivity_and_failure_stops_rebuild(
        has_zones, failure):
    calls = []
    zones = [types.SimpleNamespace(
        SetNeedRefill=lambda value: calls.append(("dirty", value)))] if has_zones else []
    board = types.SimpleNamespace(
        SetModified=lambda: calls.append("modified"), Zones=lambda: iter(zones),
        BuildConnectivity=lambda: calls.append("connectivity"))

    def fill(items):
        assert items == zones
        calls.append("fill")
        if failure == "raise":
            raise RuntimeError("test refill failure")
        return False if failure == "false" else None

    pcbnew = types.SimpleNamespace(
        ZONE_FILLER=lambda target: types.SimpleNamespace(Fill=fill))
    if failure:
        with pytest.raises(RuntimeError, match="copper has already been applied"):
            _refill_and_rebuild(board, pcbnew)
        assert calls == ["modified", ("dirty", True), "fill"]
    else:
        _refill_and_rebuild(board, pcbnew)
        assert calls == (["modified", ("dirty", True), "fill", "connectivity"]
                         if has_zones else ["modified", "connectivity"])


def test_apply_uses_zone_refill_boundary():
    source = (ROOT / "kicad_krt_gloss" / "board_adapter.py").read_text(
        encoding="utf-8")
    apply_source = source[source.index("def apply_gloss("):]
    assert "_refill_and_rebuild(board, pcbnew)" in apply_source
    assert "board.BuildConnectivity()" not in apply_source


def test_pcm_presentation_keeps_authorship_and_plain_krt_link():
    metadata = json.loads((ROOT / "kicad_krt_gloss" / "metadata.json").read_text(
        encoding="utf-8"))
    assert metadata["author"]["name"] == "Frantz with ChatGPT/Codex (OpenAI)"
    assert metadata["maintainer"]["name"] == "Frantz"
    assert metadata["author"]["contact"]["github"] == (
        "https://github.com/fca1/kicad_krt_gloss")
    assert metadata["description_full"].endswith(
        "\n\nVery based on KiCad Routing Tools (KRT) by DrAndyHaas\n"
        "https://github.com/drandyhaas/KiCadRoutingTools")


def test_selection_uses_only_selected_straight_segments_for_net_ids():
    board = Board()
    board.tracks.extend([Item(12), Item(13)])
    board.tracks[-2].GetClass = lambda: "PCB_VIA"
    board.tracks[-1].GetClass = lambda: "PCB_ARC"

    assert selected_net_ids(board) == [7]


def test_pad_or_footprint_selection_does_not_designate_a_net():
    board = Board()
    board.tracks = []

    assert selected_net_ids(board) == []


def test_exclusive_two_pad_selection_returns_centre_spacing_in_mm():
    class Pad:
        def __init__(self, x, y, selected=True):
            self.point = types.SimpleNamespace(x=x, y=y)
            self.selected = selected

        def GetClass(self): return "PCB_PAD"
        def IsSelected(self): return self.selected
        def GetPosition(self): return self.point

    first, second = Pad(1_000_000, 2_000_000), Pad(4_000_000, 6_000_000)
    board = types.SimpleNamespace(GetSelectedItems=lambda: [first, second])
    with patch.dict(sys.modules, {"pcbnew": types.SimpleNamespace(
            ToMM=lambda value: value / 1_000_000)}):
        assert selected_pad_pair_distance_mm(board) == pytest.approx(5.0)


def test_pad_pair_shortcut_rejects_any_non_pad_selection():
    pad = types.SimpleNamespace(GetClass=lambda: "PCB_PAD")
    track = types.SimpleNamespace(GetClass=lambda: "PCB_TRACK")
    board = types.SimpleNamespace(GetSelectedItems=lambda: [pad, pad, track])
    assert selected_pad_pair_distance_mm(board) is None


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


def test_checked_nets_scope_ignores_unchecked_seeds_and_includes_added_nets():
    source = (ROOT / 'kicad_krt_gloss' / 'action_plugin.py').read_text(encoding='utf-8')
    cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body
                  if isinstance(node, ast.FunctionDef) and node.name == '_prepare_checked_nets')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'scope', 'exec'), namespace)
    segments = [types.SimpleNamespace(net_id=i) for i in (1, 2, 2, 3)]
    data = types.SimpleNamespace(segments=segments)
    plugin = types.SimpleNamespace(
        _prepare_selection=lambda *_: (data, [segments[0], segments[1]]),
        _modifiable_net_rows=lambda *_: [('N1', 1), ('N2', 2), ('N3', 3)])
    resolve = namespace['_prepare_checked_nets']
    ready, codes = resolve(plugin, None, None, ['N2', 'N3'])
    assert codes == [2, 3]
    assert ready[1] == [segments[1], segments[3]]
    assert resolve(plugin, None, None, [])[0] is None
    assert resolve(plugin, None, None, ['deleted'])[0] is None


def test_dynamic_highlight_add_remove_clear_without_item_selection():
    from kicad_krt_gloss.selection import highlight_net_names
    highlighted = set()
    enabled = []
    board = types.SimpleNamespace(
        GetNetsByNetcode=lambda: {i: types.SimpleNamespace(GetNetname=lambda i=i: f'N{i}')
                                 for i in (0, 1, 2)},
        ResetNetHighLight=highlighted.clear,
        SetHighLightNet=lambda code, multi: highlighted.add(code),
        HighLightON=enabled.append)
    with patch.dict(sys.modules, {'pcbnew': types.SimpleNamespace(Refresh=lambda: None)}):
        highlight_net_names(board, ['N1', 'N2'])
        assert highlighted == {1, 2} and enabled[-1]
        highlight_net_names(board, ['N2'])
        assert highlighted == {2}
        highlight_net_names(board, [])
        assert not highlighted and not enabled[-1]


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


def test_packaged_rust_binary_uses_a_content_addressed_cache(
        tmp_path, monkeypatch):
    root = tmp_path / "KRT"
    rust_dir = root / "rust_router"
    rust_dir.mkdir(parents=True)
    source = rust_dir / "grid_router-windows-x86_64.pyd"
    source.write_bytes(b"first packaged binary")
    cache_root = tmp_path / "cache"

    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(cache_root))

    first = runtime._resolve_rust_binary(root)
    assert first.name == "grid_router.pyd"
    assert first.read_bytes() == b"first packaged binary"

    # Simulate an update while KiCad may still have the first path loaded and
    # locked: a changed binary must be written to a different directory.
    source.write_bytes(b"second packaged binary")
    second = runtime._resolve_rust_binary(root)
    assert second != first
    assert first.read_bytes() == b"first packaged binary"
    assert second.read_bytes() == b"second packaged binary"


def test_rust_cache_reuses_identical_binary_after_reinstallation(tmp_path, monkeypatch):
    root = tmp_path / "KRT"
    rust = root / "rust_router"
    rust.mkdir(parents=True)
    source = rust / "grid_router-windows-x86_64.pyd"
    source.write_bytes(b"same binary")
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(tmp_path))
    cached = runtime._resolve_rust_binary(root)
    runtime.os.utime(source, ns=(cached.stat().st_atime_ns,
                               cached.stat().st_mtime_ns + 10_000_000_000))
    with patch.object(runtime.shutil, "copy2", side_effect=PermissionError("locked")):
        assert runtime._resolve_rust_binary(root) == cached


def test_rust_cache_repairs_same_size_corruption(tmp_path, monkeypatch):
    root = tmp_path / "KRT"
    rust = root / "rust_router"
    rust.mkdir(parents=True)
    source = rust / "grid_router-windows-x86_64.pyd"
    source.write_bytes(b"valid")
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(tmp_path))
    cached = runtime._resolve_rust_binary(root)
    cached.write_bytes(b"wrong")
    assert runtime._resolve_rust_binary(root).read_bytes() == b"valid"
    assert not list(cached.parent.glob("*.tmp"))


def test_dialog_has_a_top_level_sizer_for_panel_and_buttons():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert "panel.SetSizer(content)" in source
    assert 'self.notebook.AddPage(panel, "General")' in source
    assert 'self.notebook.AddPage(panel, "Gloss")' in source
    assert 'self.notebook.AddPage(log_panel, "Log")' in source
    assert 'self.notebook.AddPage(about, "About")' in source
    assert "outer.Add(self.notebook, 1, wx.EXPAND)" in source
    assert "self.SetSizerAndFit(outer)" in source


def test_dialog_configuration_is_partitioned_by_action_scope():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")

    general = source[source.index("GENERAL_DEFAULTS = {"):
                     source.index("GLOSS_DEFAULTS = {")]
    gloss = source[source.index("GLOSS_DEFAULTS = {"):
                   source.index("CENTERING_DEFAULTS = {")]
    centering = source[source.index("CENTERING_DEFAULTS = {"):
                       source.index("DEFAULTS = GENERAL_DEFAULTS")]

    assert '"selection_uses_elementary_branches"' in general
    assert '"grid_step"' in general
    assert '"budget_seconds"' in general
    assert '"move_vias"' in gloss
    assert '"stay_in_corridor"' not in gloss
    assert '"centering_proximity_mm"' in centering
    assert '"centering_build_new_segments"' not in centering
    assert source.index('AddPage(panel, "General")') < source.index(
        'AddPage(panel, "Gloss")') < source.index(
            'AddPage(panel, "Centering")')


def test_dialog_keeps_a_post_run_log_with_krt_style_controls():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert 'label="Clear Log"' in source
    assert 'label="Copy Log"' in source
    assert "wx.TheClipboard.SetData" in source
    assert 'label="Gloss"' in source
    assert 'label="Close"' in source
    assert "wx.TE_READONLY" in source
    assert 'self.notebook.AddPage(panel, "Centering")' in source
    assert 'label="Centering"' in source
    assert 'label="Add KiCad selection"' in source
    assert 'label="Replace with KiCad selection"' in source
    assert 'label="Clear selection"' in source
    assert "on_import_centering" in source
    assert 'wx.EVT_LISTBOX, self._on_centering_net_row_selected' in source
    assert "def _on_centering_net_row_selected" in source
    assert "Preview the clicked net without changing the checked action scope." in source
    assert 'label="Refresh"' in source
    assert "def _on_refresh_proximity" in source
    assert "def _clear_centering_highlight" in source
    assert source.index("def _create_centering_selection") < source.index(
        "def _create_centering_tab")
    assert source.count("self._clear_centering_highlight()") >= 2
    assert "wx.CallAfter(self._clear_centering_highlight)" in source
    assert "panel, min=0.0, max=5.0" in source
    assert "centering_build_multi_door_path" not in source
    assert "centering_build_new_segments" not in source
    assert "No eligible door for the selected nets" in source

    action = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert '_last_log = ""' in action
    assert "initial_log=self.__class__._last_log" in action
    assert "dialog.Show()" in action
    assert "dialog.ShowModal()" not in action
    assert "on_import_centering=import_centering_selection" in action
    assert "on_refresh_proximity=lambda: KICAD.selected_pad_pair_distance_mm(board)" in action
    assert "parent.Bind(wx.EVT_CLOSE, close_dialog_with_parent)" in action
    assert "dialog = GlossSettingsDialog(\n                None" in action
    assert 'print("\\n=== Track Gloss result ===")' in action
    assert 'stats.get(\'krt_after_mm\'' in action


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
    assert 'self.selected_net_label.SetLabel(f"Selected Nets: {len(names)}")' in source


def test_pcm_package_includes_the_about_logo():
    source = (ROOT / "package_pcm.py").read_text(encoding="utf-8")
    assert '"icon_24.png", "icon_64.png"' in source
    assert '"kicad_bridge.py"' in source
    assert 'dialog_images = plugins / "img_dlg"' in source
    assert 'PLUGIN / "img_dlg" / name' in source


def test_dialog_exposes_the_integrated_gloss_options_by_public_name():
    source = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert '\"move_vias\": True' in source
    assert '\"g4_max_passes\": 1' in source
    assert "enable_g4" not in source
    assert source.count("SetToolTip(") >= 2
    assert 'label="Use elementary branches"' in source
    assert '"move_vias", "Movable vias"' in source
    assert '"stay_in_corridor", "Stay in corridor (prototype)"' not in source
    assert 'label="Proximity max"' in source
    assert 'label="G4 passes:"' in source
    assert "can take significant time" in source
    assert "self._selected_count = selected_count" in source
    assert "if self._selected_count == 1:" in source
    assert "def _create_gloss_illustration" in source
    assert 'label="G3.3' not in source
    assert 'label="G3.4' not in source
    assert '"enable_g3_3": True' not in source[source.index("def values(self):"):]
    assert '"enable_g3_4": True' not in source[source.index("def values(self):"):]
    assert 'label="Select branch"' in source
    assert "wx.STAY_ON_TOP" in source
    assert 'label="Gloss Operations"' in source
    assert 'label="Calculation Settings / Execution Limit"' in source
    assert '_DIALOG_IMAGES, "selection_scope_illustration.png"' in source
    assert "wx.ToolTip.SetDelay(250)" in source
    assert "must save strictly more than this value" in source
    assert "KRT defaults to 0.1 mm" not in source
    assert "For a direct KRT API call" not in source
    assert '"budget_seconds": 20.0' in source
    assert 'label="Time budget:"' in source
    assert "min=10.0, max=240.0" in source
    assert "inc=10.0" in source

    action = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert 'budget_seconds=values["budget_seconds"]' in action


def test_settings_dialog_is_shown_unless_exactly_one_net_is_selected():
    source = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert "values = dict(self.__class__._settings)" in source
    assert "if len(net_ids) != 1:" in source
    assert source.index("if len(net_ids) != 1:") < source.index(
        "dialog = GlossSettingsDialog")


def test_exclusive_pad_pair_opens_centering_with_its_spacing_as_proxi():
    action = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    dialog = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert 'values["centering_proximity_mm"] = pad_spacing' in action
    assert 'initial_tab="Centering" if open_centering else None' in action
    assert 'if self.notebook.GetPageText(index) == initial_tab:' in dialog


def test_plugin_selection_mode_defaults_to_be_and_cli_stays_net_only():
    dialog = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    action = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    cli = (ROOT / "gloss.py").read_text(encoding="utf-8")
    key = '"selection_uses_elementary_branches"'
    assert dialog.index(f"{key}: True") < dialog.index('"move_vias": True')
    assert "Selected elementary branches:" not in dialog
    assert 'selection.Add(selected_net, 0, wx.ALIGN_CENTER' in dialog
    assert "bounded by pads, free ends or T/X" in dialog
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


def test_gloss_results_return_to_the_log_without_a_success_modal():
    source = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    dialog = (ROOT / "kicad_krt_gloss" / "settings_dialog.py").read_text(
        encoding="utf-8")
    assert "The board was modified but not saved." not in source
    assert "if not show_progress:" in source
    assert 'self._show_action_tab("Log")' in dialog


def test_single_selected_net_runs_without_the_progress_dialog():
    source = (ROOT / "kicad_krt_gloss" / "action_plugin.py").read_text(
        encoding="utf-8")
    assert "values, net_ids, show_progress=False" in source
    assert "if show_progress:" in source
    assert source.index("if show_progress:") < source.index(
        "GlossProgressDialog(parent, session)")
    assert "outcome = run_final_gloss(" in source


def test_cli_exposes_optional_auto_or_explicit_debug_layer():
    source = (ROOT / "gloss.py").read_text(encoding="utf-8")
    assert '"--debug-layer"' in source
    assert 'choices=("auto",)' in source
    assert 'write_cli_debug_overlay(' in source
    assert ('"--stay-in-corridor", action="store_true",\n'
            '                        help=argparse.SUPPRESS') in source


def test_plugin_renders_the_complete_final_delta_once():
    source = (ROOT / "kicad_krt_gloss" / "board_adapter.py").read_text(
        encoding="utf-8")
    assert "overlay_count = add_changes_to_board(" in source
    assert "if overlay_count:" in source
    assert "changes_by_stage" not in source
    assert "debug overlay skipped" in source


def test_plugin_config_delegates_dru_rules_to_krt():
    class NetClass:
        def GetTrackWidth(self): return 200000
        def GetClearance(self): return 100000
        def GetViaDiameter(self): return 400000
        def GetViaDrill(self): return 200000

    class NetSettings:
        def GetDefaultNetclass(self): return NetClass()
        def GetEffectiveNetClass(self, _name): return NetClass()
        def GetNetclasses(self): return {}

    class Settings:
        m_NetSettings = NetSettings()
        m_CopperEdgeClearance = 150000
        m_HoleToHoleMin = 250000

    class LiveBoard:
        def GetDesignSettings(self): return Settings()
        def GetFileName(self): return "example.kicad_pcb"

    pcb = types.SimpleNamespace(
        board_info=types.SimpleNamespace(copper_layers=["F.Cu", "B.Cu"]),
        nets={1: types.SimpleNamespace(name="N1")},
        source_path="example.kicad_pcb")
    pcbnew = types.SimpleNamespace(ToMM=lambda value: value / 1e6)
    with (patch.dict(sys.modules, {"pcbnew": pcbnew}),
          patch("dgloss.rules.install_layer_clearances") as install_layers,
          patch("dgloss.rules.install_track_clearances") as install_tracks):
        config = build_krt_config(LiveBoard(), pcb, 0.1, net_ids=[1])
    install_layers.assert_called_once_with(
        config, None, "example.kicad_pcb", pcb)
    install_tracks.assert_called_once_with(
        config, None, "example.kicad_pcb", pcb, routed_net_ids=[1])
    assert config.track_width == 0.2
    assert config.via_size == 0.4
    assert config.net_clearances[1] == 0.1
    assert config.board_edge_clearance == 0.15
    assert config.hole_to_hole_clearance == 0.25
    assert config.rules.board_min["min_hole_to_hole"] == 0.25


def test_rule_installation_retains_live_table_after_file_channels():
    from design_rules import DesignRules
    from dgloss.rules import install_gloss_rules
    from routing_config import GridRouteConfig

    live = DesignRules(board_min={"min_clearance": 0.25})
    disk = DesignRules(board_min={"min_clearance": 0.1},
                       fab_floor={"clearance": 0.09})
    config = GridRouteConfig()
    pcb = types.SimpleNamespace(source_path="board.kicad_pcb")
    with (patch("dgloss.rules.install_layer_clearances",
                side_effect=lambda *args: setattr(config, "rules", disk)),
          patch("dgloss.rules.install_track_clearances")):
        result = install_gloss_rules(config, pcb, [1], rules=live)
    assert result is live and config.rules is live
    assert config.rules.board_min["min_clearance"] == 0.25
    assert config.rules.fab_floor == {"clearance": 0.09}


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

    class PadstackVia(NativeVia):
        def GetFrontWidth(self): return 0.4
        def GetWidth(self):
            raise AssertionError("KiCad 10 layerless via width must not be called")

    assert _native_via_key(board, pcbnew, PadstackVia()) == _krt_via_key(via)


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
