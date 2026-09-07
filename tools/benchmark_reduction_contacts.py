"""Read-only, bounded board comparison; prototype hooks exist only in this process."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gloss
from dgloss import GlossConfig
from dgloss import algorithm, local_gloss
from dgloss.pipeline import run_final_gloss
from net_queries import calculate_route_length
from tools.probe_same_net_contacts import ContactProbe


def run(path, mode, budget):
    log = io.StringIO()
    counters = dict(queries=0, builds=0, extra_rejections=0, exact_pairs=0,
                    old_seconds=0., build_seconds=0., query_seconds=0.)
    samples = []
    old_check = algorithm._touches_other_same_net
    last_outside, probe = None, None

    def check(candidate, outside, vias, anchors):
        nonlocal last_outside, probe
        counters['queries'] += 1
        start = perf_counter()
        old = old_check(candidate, outside, vias, anchors)
        counters['old_seconds'] += perf_counter() - start
        if mode != 'contacts' or old:
            return old
        start = perf_counter()
        # Retain objects, not bare ids; rebuild on any outside-copper change.
        if (last_outside is None or len(outside) != len(last_outside) or
                any(a is not b for a, b in zip(outside, last_outside))):
            probe = ContactProbe(outside)
            last_outside = list(outside)
            counters['builds'] += 1
        counters['build_seconds'] += perf_counter() - start
        start = perf_counter()
        count = probe.exact_calls
        rejected = probe.rejects(candidate, anchors)
        counters['exact_pairs'] += probe.exact_calls - count
        counters['query_seconds'] += perf_counter() - start
        if rejected:
            counters['extra_rejections'] += 1
            if len(samples) < 8:
                samples.append(dict(net=candidate[0].net_id, anchors=anchors,
                                    candidate=[vars(s) for s in candidate]))
        return rejected

    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        start = perf_counter()
        pcb = gloss.parse_kicad_pcb(str(path))
        ids = sorted({s.net_id for s in pcb.segments if s.net_id})
        cli = gloss.build_parser().parse_args([str(path), '--preview'])
        config = gloss.build_krt_config(cli, pcb, ids)
        before = dict(segments=len(pcb.segments), vias=len(pcb.vias),
                      nets=len(ids), pads=sum(map(len, pcb.pads_by_net.values())),
                      length_mm=calculate_route_length(pcb.segments))
        load_seconds = perf_counter() - start
        selected = GlossConfig(budget_seconds=budget)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(algorithm, '_touches_other_same_net', check))
            if mode == 'without_repair':
                stack.enter_context(patch.object(local_gloss, 'micro_free_candidates',
                                                  lambda candidate, minimum: [candidate]))
            start = perf_counter()
            outcome = run_final_gloss([], pcb, config, selected, net_ids=ids)
            elapsed = perf_counter() - start
        after = dict(segments=len(pcb.segments), vias=len(pcb.vias),
                     length_mm=calculate_route_length(pcb.segments))
    return dict(mode=mode, load_seconds=load_seconds, gloss_seconds=elapsed,
                before=before, after=after, gain_mm=before['length_mm']-after['length_mm'],
                grid_mm=config.grid_step, config=selected.as_dict(),
                contact_cost=counters, rejection_samples=samples,
                stats=outcome.stats, log=log.getvalue().splitlines())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget', type=float, default=20.)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    digest = hashlib.sha256(args.board.read_bytes()).hexdigest()
    rows = []
    modes = ['without_repair', 'repair', 'contacts']
    # Warm the parser/native libraries. Excluded from measured repetitions.
    warmup = run(args.board, 'repair', args.budget)
    print('warmup', round(warmup['gloss_seconds'], 3), flush=True)
    for repeat in range(args.repeats):
        for mode in modes[repeat % 3:] + modes[:repeat % 3]:
            row = run(args.board, mode, args.budget)
            row['repeat'] = repeat
            rows.append(row)
            print(mode, repeat, round(row['gloss_seconds'], 3),
                  'gain', round(row['gain_mm'], 3),
                  'G5', row['stats'].get('g5_valid', False), flush=True)
    unchanged = hashlib.sha256(args.board.read_bytes()).hexdigest() == digest
    result = dict(board=str(args.board.resolve()), sha256=digest,
                  input_unchanged=unchanged, warmup=warmup, runs=rows,
                  summary={mode: dict(
                      median_seconds=median(r['gloss_seconds'] for r in rows if r['mode']==mode),
                      median_gain_mm=median(r['gain_mm'] for r in rows if r['mode']==mode))
                           for mode in modes})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    assert unchanged, 'Input board changed'


if __name__ == '__main__':
    main()
