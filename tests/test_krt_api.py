"""Keep KRT imports centralized without adding runtime call overhead."""

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_api():
    spec = importlib.util.spec_from_file_location(
        "isolated_krt_api", ROOT / "dgloss" / "krt_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lazy_resolution_preserves_identity_and_resolves_once(monkeypatch):
    api = load_api()
    calls = []
    segment_type = type("Segment", (), {})
    def importer(name):
        calls.append(name)
        return SimpleNamespace(Segment=segment_type)
    monkeypatch.setattr(api, "import_module", importer)
    assert calls == []
    assert api.Segment is segment_type
    assert api.Segment is segment_type
    assert calls == ["kicad_parser"]
    with pytest.raises(AttributeError):
        api.nonexistent_symbol
    assert calls == ["kicad_parser"]


def test_krt_imports_are_confined_to_boundary():
    modules = {p.stem for p in (ROOT / "KRT" / "py_router").glob("*.py")}
    modules.update({"placement", "kicad_routing_plugin"})
    paths = [ROOT / "gloss.py"]
    paths += list((ROOT / "dgloss").glob("*.py"))
    paths += list((ROOT / "kicad_krt_gloss").glob("*.py"))
    violations = []
    for path in paths:
        if path.name == "krt_api.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in modules:
                    violations.append(f"{path.name}:{node.lineno}: {name}")
    assert not violations, violations


def test_real_core_exports_match_krt():
    from kicad_krt_gloss.runtime import configure_krt_runtime
    configure_krt_runtime()
    from dgloss import krt_api
    from kicad_parser import Segment
    from net_queries import calculate_route_length
    from check_connected import check_net_connectivity
    assert krt_api.Segment is Segment
    assert krt_api.calculate_route_length is calculate_route_length
    assert krt_api.check_net_connectivity is check_net_connectivity
