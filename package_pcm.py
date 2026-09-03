#!/usr/bin/env python3
"""Build the standalone KiCad KRT Gloss PCM archive."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "kicad_krt_gloss"
KRT = ROOT / "KRT"
VERSION = "0.1.0"
KRT_VERSION = (KRT / "VERSION").read_text(encoding="utf-8").strip()
BINARIES = (
    "grid_router-linux-x86_64.so",
    "grid_router-macos-arm64.so",
    "grid_router-macos-x86_64.so",
    "grid_router-windows-x86_64.pyd",
)


def _copytree(source, destination):
    shutil.copytree(source, destination,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", ".pytest_cache", "target",
                        "grid_router.pyd", "grid_router.so"))


def _download_binaries(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in BINARIES:
        url = ("https://github.com/drandyhaas/KiCadRoutingTools/releases/"
               f"download/v{KRT_VERSION}/{name}")
        print("Downloading " + url)
        request = urllib.request.Request(url, headers={"User-Agent": "krg"})
        with urllib.request.urlopen(request, timeout=120) as response:
            with open(destination / name, "wb") as output:
                shutil.copyfileobj(response, output)


def build(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"KiCadKrtGloss-{VERSION}.zip"
    with tempfile.TemporaryDirectory(prefix="krg-pcm-") as temporary:
        stage = Path(temporary)
        plugins = stage / "plugins"
        plugins.mkdir()
        for name in ("__init__.py", "action_plugin.py", "board_adapter.py",
                     "debug_overlay.py", "gloss_visualization.py", "runtime.py", "selection.py",
                     "settings_dialog.py", "version.py", "icon_24.png", "icon_64.png",
                     "icon_24_dark.png"):
            shutil.copy2(PLUGIN / name, plugins / name)
        package_documents = (
            (ROOT / "docs" / "AUTHORS.md", "AUTHORS.md"),
            (ROOT / "LICENSE", "LICENSE"),
            (ROOT / "NOTICE", "NOTICE"),
            (ROOT / "README.md", "README.md"),
        )
        for source, archive_name in package_documents:
            shutil.copy2(source, plugins / archive_name)
        _copytree(ROOT / "dgloss", plugins / "dgloss")

        runtime = plugins / "KRT"
        _copytree(KRT / "py_router", runtime / "py_router")
        (runtime / "kicad_routing_plugin").mkdir(parents=True)
        shutil.copy2(KRT / "kicad_routing_plugin" / "deps_check.py",
                     runtime / "kicad_routing_plugin" / "deps_check.py")
        shutil.copy2(KRT / "requirements.txt", runtime / "requirements.txt")
        shutil.copy2(KRT / "LICENSE", runtime / "LICENSE")
        shutil.copy2(KRT / "VERSION", runtime / "VERSION")
        _download_binaries(runtime / "rust_router")

        shutil.copy2(PLUGIN / "metadata.json", stage / "metadata.json")
        resources = stage / "resources"
        resources.mkdir()
        shutil.copy2(PLUGIN / "icon_64.png", resources / "icon.png")
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage).as_posix())

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive_path) as archive:
        install_size = sum(item.file_size for item in archive.infolist())
    sidecar = archive_path.with_suffix(".meta.json")
    sidecar.write_text(json.dumps({
        "version": VERSION,
        "krt_version": KRT_VERSION,
        "sha256": digest,
        "download_size": archive_path.stat().st_size,
        "install_size": install_size,
    }, indent=2) + "\n", encoding="utf-8")
    print(archive_path)
    print("sha256=" + digest)
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "dist"))
    args = parser.parse_args()
    build(args.output_dir)
