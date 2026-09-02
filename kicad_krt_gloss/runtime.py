"""Locate the KRT submodule without importing its ActionPlugin."""

from pathlib import Path
import importlib.util
import os
import platform
import shutil
import sys


def krt_root():
    package_dir = Path(__file__).resolve().parent
    for candidate in (package_dir / "KRT", package_dir.parent / "KRT"):
        if (candidate / "py_router").is_dir():
            return candidate
    raise RuntimeError(
        "KRT submodule is missing; initialize it with "
        "'git submodule update --init --recursive'")


def _resolve_rust_binary(root):
    rust_dir = root / "rust_router"
    canonical = "grid_router.pyd" if sys.platform == "win32" else "grid_router.so"
    destination = rust_dir / canonical
    if destination.exists():
        return
    machine = platform.machine().lower()
    source = None
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        source = rust_dir / "grid_router-windows-x86_64.pyd"
    elif sys.platform == "darwin" and machine == "arm64":
        source = rust_dir / "grid_router-macos-arm64.so"
    elif sys.platform == "darwin" and machine in ("amd64", "x86_64"):
        source = rust_dir / "grid_router-macos-x86_64.so"
    elif sys.platform.startswith("linux") and machine in ("amd64", "x86_64"):
        source = rust_dir / "grid_router-linux-x86_64.so"
    if source is None or not source.exists():
        raise RuntimeError("No packaged KRT Rust binary matches this platform")
    shutil.copy2(source, destination)


def configure_krt_runtime():
    """Expose only KRT's library directories to the standalone gloss."""
    root = krt_root()
    _resolve_rust_binary(root)
    for path in (root, root / "py_router", root / "rust_router"):
        value = os.fspath(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    return root


def ensure_krt_dependencies(parent=None):
    """Use KRT's own dependency installer without importing its plugin."""
    root = krt_root()
    source = root / "kicad_routing_plugin" / "deps_check.py"
    if not source.is_file():
        return True
    spec = importlib.util.spec_from_file_location("krg_krt_deps_check", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ensure_dependencies(parent)
