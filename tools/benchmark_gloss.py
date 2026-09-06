"""Read-only board benchmarks; optional profiling is NOT a wall-time benchmark.

python tools/benchmark_gloss.py board.kicad_pcb --budget 60 [--profile]
No board is saved. JSON includes input hashes, stages and convergence status.
"""

import argparse
import contextlib
import cProfile
import hashlib
import io
import json
from pathlib import Path
import pstats
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss.pipeline import run_final_gloss
from net_queries import calculate_route_length


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boards", nargs="+", type=Path)
    parser.add_argument("--budget", type=float, default=60)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--net", type=int)
    args = parser.parse_args()
    failed = False
    for path in args.boards:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        log = io.StringIO()
        profile = cProfile.Profile()
        started = perf_counter()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            pcb = gloss.parse_kicad_pcb(str(path))
            ids = ([args.net] if args.net is not None else
                   sorted({s.net_id for s in pcb.segments if s.net_id}))
            cli = gloss.build_parser().parse_args([str(path), "--preview"])
            config = gloss.build_krt_config(cli, pcb, ids)
            before = calculate_route_length(pcb.segments)
            ready = perf_counter()
            if args.profile:
                profile.enable()
            outcome = run_final_gloss(
                [], pcb, config, GlossConfig(budget_seconds=args.budget), net_ids=ids)
            if args.profile:
                profile.disable()
            finished = perf_counter()
            after = calculate_route_length(pcb.segments)
        unchanged = digest == hashlib.sha256(path.read_bytes()).hexdigest()
        valid = outcome.stats.get("g5_valid", False)
        failed |= not valid or not unchanged
        print(json.dumps({
            "board": str(path), "sha256": digest, "input_unchanged": unchanged,
            "profiled": args.profile, "grid_mm": config.grid_step,
            "load_seconds": ready - started, "gloss_seconds": finished - ready,
            "before_mm": before, "after_mm": after, "gain_mm": before - after,
            "stats": outcome.stats, "log": log.getvalue().splitlines(),
        }, default=lambda value: sorted(value) if isinstance(value, set) else str(value)),
              flush=True)
        if args.profile:
            pstats.Stats(profile, stream=sys.stdout).strip_dirs().sort_stats(
                "cumulative").print_stats(35)
            pstats.Stats(profile, stream=sys.stdout).strip_dirs().sort_stats(
                "tottime").print_stats(20)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
