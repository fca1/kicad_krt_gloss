"""Locate the KRT submodule without importing its ActionPlugin."""

from pathlib import Path
import hashlib
import importlib.util
import os
import platform
import shutil
import sys
import tempfile


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
    existing = rust_dir / canonical
    if existing.exists():
        return existing
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
    # Python imports extension modules by their canonical module filename. Keep
    # the KRT submodule immutable by materializing that name in our own cache.
    # Windows keeps an imported extension module locked until KiCad exits.
    # A content-addressed directory lets a plugin update load a new binary
    # without trying to overwrite the previous, still-loaded grid_router.pyd.
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = (Path(tempfile.gettempdir()) / "kicad_krt_gloss" /
             f"{sys.version_info.major}.{sys.version_info.minor}" /
             f"{sys.platform}-{machine}" / digest[:16])
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / canonical
    if (destination.exists() and
            hashlib.sha256(destination.read_bytes()).hexdigest() == digest):
        return destination
    # Never truncate a cached extension in place. Publish a complete copy;
    # another KiCad process may have populated this cache in the meantime.
    descriptor, temporary = tempfile.mkstemp(dir=cache, suffix=".tmp")
    os.close(descriptor)
    try:
        shutil.copy2(source, temporary)
        try:
            os.replace(temporary, destination)
        except PermissionError:
            if (not destination.exists() or
                    hashlib.sha256(destination.read_bytes()).hexdigest() != digest):
                raise
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def configure_krt_runtime():
    """Expose the packaged dgloss and KRT libraries to the plugin runtime."""
    package_dir = Path(__file__).resolve().parent
    root = krt_root()
    binary = _resolve_rust_binary(root)
    runtime_dir = binary.parent if binary is not None else root / "rust_router"
    for path in (package_dir, root, root / "py_router", runtime_dir):
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
    # PyPI distribution names need not match Python import names.
    # KRT 0.22 declares Pillow but its generic fallback tries `import Pillow`.
    module.IMPORT_TESTS.setdefault("Pillow", "from PIL import Image")
    return module.ensure_dependencies(parent)
