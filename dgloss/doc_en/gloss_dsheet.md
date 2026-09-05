# Track Gloss — user and integration guide

This guide explains how to use and observe Track Gloss. Requirements are in
[`gloss_rules.md`](gloss_rules.md); implementation is described in
[`gloss_work.md`](gloss_work.md).

## Component status

- Development branch: `main`
- Plugin version: `0.1.0`
- Integrated stage: G5
- Plugin scope: elementary branches seeded by selected straight tracks; other
  selected objects choose complete nets; no selection means all routed nets
- Trigger: once, after final KRT smooth
- Default plugin budget: 20 seconds
- Dedicated CLI: `gloss.py`

## Command-line use

The CLI follows KRT conventions for net names and patterns, `--nets`,
`--component`, `--group`, `--group-by`, `--group-scope`, and `--list-groups`.
Without a selection it processes all routed nets. CLI selections always mean
complete nets.

```text
python gloss.py input.kicad_pcb output.kicad_pcb --nets "/Cpu/*"
python gloss.py input.kicad_pcb --component U1 --preview
python gloss.py input.kicad_pcb --json-out gloss-summary.json
```

Omitted parameters are resolved through KRT from the project's Default class,
per-net classes, and `.kicad_dru` rules. The standalone grid step remains KRT's
`0.1 mm` unless `--grid-step` is explicit. Output includes a human-readable
summary, `JSON_SUMMARY`, `JSON_SUMMARY_MIN`, and optionally a full JSON file.

## Plugin use

The standalone plugin runs final KRT smooth and then Track Gloss. These dialog
options are enabled by default:

| Option | Effect |
|---|---|
| `Selection — use elementary branches` | Selected tracks designate BEs; unchecked, selection designates complete nets |
| `Track Gloss G3.1 — mobile vias` | Allows local movement of eligible vias |
| `Track Gloss G3.2 — pad terminals` | Optimizes pad terminations |
| `Track Gloss G3.3 — sliding T nodes` | Allows sliding T branches |
| `Track Gloss G3.3 — allow non-collinear rails` | Enables the T variant without a collinear rail |
| `Track Gloss G3.4 — complete via chains` | Optimizes complete chains around vias |
| `G4 — multi-net convergence passes` | Repeats G3.5 until convergence |
| `G5 — final compliance certification` | Certifies output without changing geometry |
| `Gloss time budget (s)` | 10–240 second dgloss optimization budget, in 10-second increments |

G3 ordinary-chain reduction is the always-active foundation. A disabled option
runs neither its stage nor its visualization.

A selected straight track is a seed. G0 finds its maximal elementary branch
and every stage remains within it. Several tracks may identify several branches
on several nets. When at least one straight track is selected, only those seeds
define BE scope. A selected pad, via, footprint, or zone without a straight
track retains complete-net behavior.

The dialog opens when zero or several nets are selected. With exactly one net,
processing starts immediately with the remembered settings; initial settings
use BEs. A read-only label shows the selected-net count, or `ALL` without a
selection. These are plugin-only choices: the CLI always selects complete nets.

The plugin budget defaults to 20 seconds and can be set from 10 to 240 seconds
in 10-second increments. It cooperatively limits dgloss searches, not total
runtime including final KRT smooth, certification, and KiCad application.

## Python library use

To reproduce plugin behavior:

```python
from dgloss import GlossConfig, run_final_gloss

options = GlossConfig(
    enable_g3_1=True,
    enable_g3_2=True,
    enable_g3_3=True,
    enable_g3_4=True,
    budget_seconds=20.0,
    enable_noncollinear_t_rails=True,
    enable_multipasses=True,
)
outcome = run_final_gloss(
    results, pcb_data, krt_config, options,
    seed_segments=selected_final_krt_segments,
)
```

For a caller already holding final KRT smooth output:

```python
from dgloss import run_post_smooth_gloss

outcome = run_post_smooth_gloss(
    results, pcb_data, krt_config, gloss_config=options,
    net_ids=selected_net_ids, krt_smooth_complete=True,
    seed_segments=selected_final_krt_segments,
)
```

`seed_segments` is optional. Without it, `net_ids` means complete nets. With
it, objects must be the `Segment` instances present in final `pcb_data`; their
identity strictly limits changes without copying copper.

The second form is strictly post-smooth: it rebuilds context but never reruns
`smooth_octolinear_chains()`. `krt_smooth_complete=True` prevents duplication
of canonical families just processed by final smooth. This is the public API
for direct KRT integration. The standalone CLI does not set this certificate.

G0 builds context once, including with G4. It first excludes length/timing
groups, coupled differential pairs, impedance nets, nets containing locked
copper, and nets containing arcs. Excluded nets remain obstacles.

## Configuration

`GlossConfig` is independent of `GridRouteConfig`; KRT does not depend on its
options.

| Field | Default | Meaning |
|---|---:|---|
| `enable_g3_1` | `True` | Enable G3.1 |
| `enable_g3_2` | `True` | Enable G3.2 |
| `enable_g3_3` | `True` | Enable G3.3 |
| `enable_g3_4` | `True` | Enable G3.4 |
| `budget_seconds` | `20.0` | Global post-smooth budget |
| `enable_noncollinear_t_rails` | `True` | Enable non-collinear G3.3 variant |
| `enable_multipasses` | `True` | Enable G4 convergence passes over G3.5 |

## Machine-readable result

`GlossOutcome` provides:

- `input_strip_segments` and `input_strip_vias`, to remove from KRT output;
- `changes`, structured old/new objects;
- `stats`, structured data for tests, reports, and CLI output.

The global summary includes processed and improved nets, before/after lengths,
segment and via changes, separate dgloss and KRT gains, elapsed time, budget
state, and connectivity regressions. `nets_excluded`, `excluded_net_ids`, and
`exclusion_reasons` describe G0 exclusions. `branch_scoped`,
`elementary_branches`, and the G0 log describe active BE scope.

Final segment reduction also exposes `equal_length_segment_reduction`,
`segments_merged`, `merge_joints`, `equal_length_algorithm_ms`, and
`merge_algorithm_ms`. G5 exposes `g5_valid`, `g5_segments_certified`,
`g5_segments_geometry_preserved`, `g5_vias_certified`, and `g5_algorithm_ms`.

The log prints one short line per stage and a global line:

```text
Track Gloss G3.5: 120 nets processed, 8 improved, -12.3400 mm, 8500.0 ms
```

## KiCad visualization

Visualization never affects algorithmic decisions and is entirely in the
plugin adapter; dgloss has no `pcbnew` dependency. It shows changed copper:
old tracks dashed, new tracks solid, and old/new positions of moved vias.

From G4 onward one layer shows the final delta. The plugin reuses a layer named
`TrackGloss Changes`; otherwise it selects the first free `User.N` layer. It
never takes a renamed or foreign-owned layer. `add_layer_user()` enables and
shows the selected layer. User layers are non-copper and are absent from Gerber
output unless explicitly added to a plot job.

The CLI creates no visualization by default. `--debug-layer auto` applies the
same selection rule; `--debug-layer User.N` requests a specific free layer from
User.1 to User.9. If none is available, only visualization is skipped.

## Failure behavior

If a stage fails or final certification rejects the result, all dgloss changes
from the call are rolled back. Final KRT smooth copper is preserved and the
plugin can return it to KiCad.
