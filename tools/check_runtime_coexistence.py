"""Vérifie les deux moteurs réels ; option Gloss sur une carte détachée."""

import argparse
import importlib
import importlib.util
import os
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin", type=Path)
    parser.add_argument("standard", type=Path)
    parser.add_argument("--order", choices=("gloss-first", "krt-first"), required=True)
    parser.add_argument("--board", type=Path)
    args = parser.parse_args()
    plugin = args.plugin.resolve()
    standard = args.standard.resolve()
    # Reproduit la découverte du plugin standard avant son premier lancement.
    for path in (standard, standard / "py_router", standard / "rust_router",
                 standard / "py_placer", standard / "py_tools"):
        sys.path.append(str(path))

    def krt():
        route = importlib.import_module("route")
        assert Path(route.__file__).is_relative_to(standard)
        assert importlib.import_module("startup_checks").check_rust_library() == "0.23.0"
        return route

    def gloss():
        spec = importlib.util.spec_from_file_location("coexistence_runtime", plugin / "runtime.py")
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        before = list(sys.path)
        runtime.configure_krt_runtime()
        import dgloss.krt_api as api
        assert api.Segment.__module__ == "_gloss_embedded_krt.kicad_parser"
        startup = importlib.import_module("_gloss_embedded_krt.startup_checks")
        assert startup.check_rust_library() == "0.23.0"
        importlib.import_module("_gloss_embedded_krt.kicad_routing_plugin.fanout_gui")
        assert runtime.ensure_krt_dependencies()
        if args.board:
            os.environ["KRG_TEST_PLUGIN_ROOT"] = str(plugin)
            sys.argv = ["check_branch_memory_native.py", str(args.board.resolve()),
                        "--scope", "multiple"]
            runpy.run_path(str(Path(__file__).with_name("check_branch_memory_native.py")),
                           run_name="__main__")
        added = set(sys.path) - set(before)
        assert not any(Path(p).is_relative_to(plugin / "KRT") for p in added)

    if args.order == "krt-first":
        original = krt()
        gloss()
        assert krt() is original
    else:
        gloss()
        krt()
    # Contrôle de provenance des deux classes et des deux bibliothèques Rust.
    for name in ("route", "startup_checks", "kicad_parser", "grid_router"):
        module = importlib.import_module(name)
        assert Path(module.__file__).is_relative_to(standard), (name, module.__file__)
    print("PASS coexistence", args.order)


if __name__ == "__main__":
    main()
