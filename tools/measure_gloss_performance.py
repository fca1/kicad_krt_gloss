"""Measure one untouched board in a fresh process, without saving it.

Use --source-root for the code under test and --runtime-root for an unpacked
official plugin runtime. Run baseline/current sequentially in alternating order.
The budget is deliberately generous: an expired run is not a valid comparison.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import types


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root, directories):
    result = hashlib.sha256()
    for directory in directories:
        for path in sorted((root / directory).rglob('*.py')):
            result.update(path.relative_to(root).as_posix().encode())
            result.update(path.read_bytes())
    return result.hexdigest()


def stable_stats(value):
    if isinstance(value, dict):
        return {key: stable_stats(item) for key, item in value.items()
                if not key.endswith('_ms') and key not in ('seconds', 'budget_seconds')}
    if isinstance(value, (list, tuple)):
        return [stable_stats(item) for item in value]
    if isinstance(value, set):
        return sorted(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--corridor', action='store_true')
    parser.add_argument('--g4-passes', type=int, default=1)
    args = parser.parse_args()
    source, runtime = args.source_root.resolve(), args.runtime_root.resolve()
    os.environ['KRG_IPC'] = '1'
    package = types.ModuleType('kicad_krt_gloss')
    package.__path__ = [str(source / 'kicad_krt_gloss')]
    sys.modules[package.__name__] = package
    # Resolve the official binary without modifying the KRT checkout or its cache.
    name = 'kicad_krt_gloss.runtime'
    spec = importlib.util.spec_from_file_location(name, runtime / 'runtime.py')
    bootstrap = importlib.util.module_from_spec(spec)
    sys.modules[name] = bootstrap
    spec.loader.exec_module(bootstrap)
    bootstrap.configure_krt_runtime()
    sys.path.insert(0, str(source))
    import gloss
    import dgloss
    from dgloss import GlossConfig, run_final_gloss
    from _gloss_embedded_krt import grid_router
    assert Path(dgloss.__file__).resolve().parent == source / 'dgloss'
    inputs = [args.board.with_suffix(s) for s in ('.kicad_pcb', '.kicad_pro', '.kicad_dru')]
    before = {str(path.resolve()): digest(path) for path in inputs if path.exists()}
    log = io.StringIO()
    with redirect_stdout(log):
        started = perf_counter()
        pcb = gloss.parse_kicad_pcb(str(args.board.resolve()))
        nets = sorted({s.net_id for s in pcb.segments if s.net_id})
        cfg = gloss.build_krt_config(
            gloss.build_parser().parse_args([str(args.board.resolve()), '--preview']), pcb, nets)
        ready = perf_counter()
        outcome = run_final_gloss([], pcb, cfg,
            GlossConfig(budget_seconds=600, g4_max_passes=args.g4_passes,
                        stay_in_corridor=args.corridor), net_ids=nets)
        finished = perf_counter()
    after = {str(path.resolve()): digest(path) for path in inputs if path.exists()}
    assert before == after, 'Input PCB/project/rules changed'
    assert outcome.stats.get('g5_valid'), 'G5 failed'
    assert not outcome.stats.get('gloss', {}).get('budget_expired'), 'Budget expired'
    geometry = (
        sorted((s.net_id, s.layer, s.width, s.start_x, s.start_y, s.end_x, s.end_y,
                bool(s.graphic), bool(s.locked)) for s in pcb.segments),
        sorted((v.net_id, v.x, v.y, v.size, v.drill, tuple(v.layers), bool(v.locked))
               for v in pcb.vias))
    record = dict(source=str(source), source_sha256=tree_digest(source, ['dgloss']),
                  krt_sources_sha256=tree_digest(runtime, ['KRT/py_router']),
                  inputs=before, corridor=args.corridor,
                  g4_passes=args.g4_passes, seconds=finished-ready, load_seconds=ready-started,
                  geometry_sha256=hashlib.sha256(json.dumps(geometry).encode()).hexdigest(),
                  stats=outcome.stats, stable_stats=stable_stats(outcome.stats),
                  rust_sha256=digest(Path(grid_router.__file__)),
                  krt_version=(runtime/'KRT/VERSION').read_text().strip(),
                  log=log.getvalue().splitlines())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, default=str), encoding='utf-8')
    print(json.dumps({key: record[key] for key in
                     ('seconds', 'load_seconds', 'geometry_sha256', 'corridor')}, indent=2))


if __name__ == '__main__':
    main()
