"""Charge les sources KRT intactes dans un espace de modules privé à Gloss."""

import builtins
import importlib
import importlib.abc
import importlib.util
from pathlib import Path
import sys
import types

NAMESPACE = "_gloss_embedded_krt"


class _PrivateSys(types.ModuleType):
    """Les ajouts de chemins de KRT ne doivent pas modifier ceux de KiCad."""

    def __init__(self):
        super().__init__("sys")
        self.path = list(sys.path)

    def __getattr__(self, name):
        return getattr(sys, name)

    def __setattr__(self, name, value):
        if name == "path" or name.startswith("__"):
            super().__setattr__(name, value)
        else:
            setattr(sys, name, value)


class _SourceLoader(importlib.abc.Loader):
    def __init__(self, finder, source):
        self.finder = finder
        self.source = source

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        # Un dictionnaire propre au module garde aussi les imports différés
        # dans cet espace privé, sans remplacer builtins.__import__ globalement.
        module.__builtins__ = dict(vars(builtins),
                                   __import__=self.finder.import_local)
        exec(compile(self.source.read_bytes(), str(self.source), "exec"),
             module.__dict__)


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, root, binary):
        self.root = Path(root).resolve()
        self.binary = Path(binary)
        self.paths = [self.root / name for name in
                      ("py_router", "py_placer", "py_tools")] + [self.root]
        self.names = {"grid_router"}
        for path in self.paths:
            if path.is_dir():
                self.names.update(item.stem for item in path.glob("*.py"))
                self.names.update(item.name for item in path.iterdir()
                                  if item.is_dir() and
                                  (item / "__init__.py").is_file())
        self.private_sys = _PrivateSys()

    def import_local(self, name, globals=None, locals=None, fromlist=(), level=0):
        if not level and name == "sys":
            return self.private_sys
        if not level and name.split(".")[0] in self.names:
            qualified = NAMESPACE + "." + name
            module = builtins.__import__(qualified, globals, locals,
                                         fromlist or ("__name__",), 0)
            return module if fromlist else sys.modules[
                NAMESPACE + "." + name.split(".")[0]]
        return builtins.__import__(name, globals, locals, fromlist, level)

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(NAMESPACE + "."):
            return None
        relative = fullname[len(NAMESPACE) + 1:]
        if relative == "grid_router":
            return importlib.util.spec_from_file_location(fullname, self.binary)
        parts = relative.split(".")
        for base in self.paths:
            candidate = base.joinpath(*parts)
            package = candidate / "__init__.py"
            source = package if package.is_file() else candidate.with_suffix(".py")
            if source.is_file():
                return importlib.util.spec_from_file_location(
                    fullname, source, loader=_SourceLoader(self, source),
                    submodule_search_locations=[str(candidate)]
                    if source == package else None)
        # Un module KRT absent ne doit jamais être emprunté à l'autre plugin.
        raise ModuleNotFoundError(f"Module KRT embarqué absent : {relative}",
                                  name=fullname)


def install(root, binary):
    existing = sys.modules.get(NAMESPACE)
    if existing is not None:
        if existing.__krt_root__ != str(Path(root).resolve()):
            raise RuntimeError("Une autre copie de Gloss est chargée ; redémarrer KiCad.")
        return
    finder = _Finder(root, binary)
    package = types.ModuleType(NAMESPACE)
    package.__path__ = []
    package.__package__ = NAMESPACE
    package.__krt_root__ = str(finder.root)
    package.__spec__ = importlib.util.spec_from_loader(NAMESPACE, loader=None,
                                                     is_package=True)
    sys.modules[NAMESPACE] = package
    sys.meta_path.insert(0, finder)
