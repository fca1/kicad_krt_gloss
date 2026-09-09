"""Architectural guard for all production modules, including integrated EB."""
import ast
from pathlib import Path

from kicad_krt_gloss.kicad_bridge import KiCadBoardBridge

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ADAPTERS = {
    'kicad_bridge.py', 'selection.py', 'board_adapter.py',
    'gloss_visualization.py', 'native_branch_selection.py',
}


def test_native_access_is_confined_to_declared_adapters():
    violations = []
    native_attributes = {
        '_pcbnew', 'm_Uuid', 'GetTracks', 'GetFootprints', 'GetNetsByNetcode',
        'GetNetCode', 'GetNetname', 'GetBoard', 'GetLayerName', 'Zones', 'Pads',
        'SetBrightened', 'ClearBrightened', 'IsBrightened', 'IsSelected',
        'SetSelected', 'ClearSelected', 'BuildConnectivity', 'ToMM', 'FromMM',
    }
    paths = list((ROOT / 'kicad_krt_gloss').glob('*.py'))
    paths += list((ROOT / 'dgloss').glob('*.py')) + [ROOT / 'gloss.py']
    for path in paths:
        if path.parent.name == 'kicad_krt_gloss' and path.name in NATIVE_ADAPTERS:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                if any(alias.name == 'pcbnew' for alias in node.names):
                    if not (path.parent.name == 'kicad_krt_gloss' and
                            path.name in {'__init__.py', 'action_plugin.py'}):
                        violations.append(f'{path.name}:{node.lineno}: pcbnew import')
            if isinstance(node, ast.ImportFrom) and node.module == 'pcbnew':
                violations.append(f'{path.name}:{node.lineno}: pcbnew import')
            if isinstance(node, ast.Attribute):
                if node.attr in native_attributes:
                    violations.append(f'{path.name}:{node.lineno}: {node.attr}')
                if isinstance(node.value, ast.Name) and node.value.id == 'pcbnew':
                    if not (path.name == 'action_plugin.py' and node.attr == 'ActionPlugin'):
                        violations.append(f'{path.name}:{node.lineno}: pcbnew.{node.attr}')
            if isinstance(node, ast.ImportFrom) and node.module in {
                    'native_branch_selection', 'board_adapter', 'selection', 'gloss_visualization'}:
                violations.append(f'{path.name}:{node.lineno}: adapter import')
    assert not violations, violations


def test_bridge_owns_native_eb_dependencies(monkeypatch):
    from kicad_krt_gloss import native_branch_selection as adapter
    native, board, data, index, memory = (object() for _ in range(5))
    bridge = KiCadBoardBridge(native)
    calls = []
    monkeypatch.setattr(adapter, 'track_index', lambda *args: calls.append(args) or index)
    monkeypatch.setattr(adapter, 'capture', lambda *args: calls.append(args) or {'A': []})
    monkeypatch.setattr(adapter, 'BranchHighlighter', lambda *args: calls.append(args) or 'highlighter')
    assert bridge.branch_track_index(board, data) is index
    assert bridge.capture_branches(board, data, index, {'A'}) == {'A': []}
    assert bridge.branch_highlighter(board, memory) == 'highlighter'
    assert calls == [(board, data, native), (board, data, index, native, {'A'}),
                     (board, bridge.refresh, memory)]


def test_native_eb_adapter_is_packaged():
    assert '"native_branch_selection.py"' in (ROOT / 'package_pcm.py').read_text()
