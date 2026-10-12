"""Contrats d'import : deux moteurs différents dans le même processus."""

import importlib
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def engines(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "kicad_krt_gloss/isolated_krt.py"
    spec = importlib.util.spec_from_file_location("isolation_test_loader", source)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    # Ce test ne touche pas au moteur déjà chargé par les autres tests.
    monkeypatch.setattr(loader, "NAMESPACE", "_test_gloss_krt")
    private = tmp_path / "private"
    public = tmp_path / "public"
    (private / "py_router/pkg").mkdir(parents=True)
    public.mkdir()
    (public / "probe_engine.py").write_text("VALUE = 'public'\n")
    (private / "py_router/probe_engine.py").write_text(
        "import sys\nsys.path.insert(0, 'PRIVATE_ONLY')\nVALUE = 'private'\n"
        "def later():\n import pkg.child\n return pkg.child.VALUE\n")
    (private / "py_router/pkg/__init__.py").write_text("from . import child\n")
    (private / "py_router/pkg/child.py").write_text(
        "from probe_engine import VALUE\n")
    monkeypatch.syspath_prepend(str(public))
    before = list(sys.path)
    meta = list(sys.meta_path)
    loader.install(private, private / "unused.pyd")
    try:
        yield loader, private, before
    finally:
        sys.meta_path[:] = meta
        for name in list(sys.modules):
            if name == "probe_engine" or name.startswith("_test_gloss_krt"):
                del sys.modules[name]


@pytest.mark.parametrize("private_first", [True, False])
def test_launch_orders_keep_modules_and_delayed_imports_separate(engines, private_first):
    loader, root, before = engines
    names = ["_test_gloss_krt.probe_engine", "probe_engine"]
    if not private_first:
        names.reverse()
    modules = {name: importlib.import_module(name) for name in names}
    private = modules["_test_gloss_krt.probe_engine"]
    public = modules["probe_engine"]
    assert private.VALUE == private.later() == "private"
    assert public.VALUE == "public"
    assert private is not public
    assert sys.path == before
    assert "pkg" not in sys.modules
    assert "pkg.child" not in sys.modules
    # Une deuxième ouverture ne remplace aucun module existant.
    loader.install(root, root / "unused.pyd")
    assert importlib.import_module("_test_gloss_krt.probe_engine") is private


def test_missing_private_module_does_not_fall_back_to_public(engines):
    with pytest.raises(ModuleNotFoundError, match="embarqué absent"):
        importlib.import_module("_test_gloss_krt.pkg.missing")


def test_second_installation_requires_restart(engines, tmp_path):
    loader, _, _ = engines
    with pytest.raises(RuntimeError, match="redémarrer"):
        loader.install(tmp_path / "other", tmp_path / "unused.pyd")
