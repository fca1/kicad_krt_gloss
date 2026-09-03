# Track Gloss — KRT integration Python API

This document defines the Python entry point that KRT may call directly. The
API remains independent of the plugin, `pcbnew`, and KiCad presentation.

## Purpose

`run_post_smooth_gloss()` lets KRT pass its already-built routing state to
dgloss without converting through a graphical API or triggering another
implicit smooth.

Its primary use is one call after final KRT smooth. It remains public and
compatible with KRT structures so the gloss may later be used like `smooth`,
participate in autorouting, or run at another point chosen by KRT. KRT owns call
timing; dgloss owns its algorithms and requires no KRT or Rust modification.

## Target contract

```python
run_post_smooth_gloss(
    results,
    pcb_data,
    config,
    gloss_config=None,
    *,
    net_ids=None,
    krt_strips=None,
    krt_stats=None,
    krt_ms=0.0,
    excluded_net_ids=None,
    krt_smooth_complete=False,
    seed_segments=None,
)
```

`net_ids` is optional for backward compatibility and is supported by the
standalone `kicad_krt_gloss` repository.

## Parameters

| Parameter | Origin | Role |
|---|---|---|
| `results` | KRT | KRT-convention result list to extend |
| `pcb_data` | KRT | Complete PCB state at call time |
| `config` | KRT | `GridRouteConfig`, including the actual `grid_step` |
| `gloss_config` | dgloss | Gloss-specific options; defaults when absent |
| `net_ids` | KRT or plugin | Complete nets; `None` or empty means all nets |
| `krt_strips` | KRT | Segments already replaced by the preceding stage |
| `krt_stats` | KRT | Statistics from the preceding KRT stage |
| `krt_ms` | KRT | KRT time kept separate from dgloss time |
| `excluded_net_ids` | caller | Additional input-boundary exclusions, especially native arcs |
| `krt_smooth_complete` | KRT | Certifies that final smooth is already complete |
| `seed_segments` | KRT or plugin | Final `Segment` instances seeding elementary branches |

Without `seed_segments`, selection covers complete nets. With seeds, G0
resolves their elementary-branch union once and all stages remain within it.
Seeds must be instances in the supplied post-smooth `pcb_data`, not geometric
copies. The remainder of each net stays as fixed copper for obstacles,
topology, and final certification.

G0 combines scope with KRT protections: length/timing groups, coupled
differential pairs, impedance, and locked copper. Arcs found in KRT data or
reported through `excluded_net_ids` are also excluded. An exclusion always
covers the complete net and explicit selection cannot override it.

Default `GlossConfig.enable_multipasses` asks G4 to repeat the complete G3.5
pipeline in alternating net order. Each pass calls the private G3.5 core once
with the ordered list. Every pass reuses the context, grid, and obstacle base
built once by G0. Public `run_post_smooth_gloss()` is called only once.
`enable_noncollinear_t_rails` controls the corresponding G3.3 variant.

## Grid

For a direct KRT call, `config.grid_step` is mandatory and is the actual KRT
resolution. Dgloss substitutes neither an interface grid, nor a copper-derived
value, nor micron-level search. The `0.1 mm` default applies only to standalone
use without a previous KRT configuration.

## Preconditions

- `pcb_data` is a complete, coherent routing state.
- `config` matches it and contains the rules needed to rebuild obstacles.
- The caller does not concurrently mutate supplied objects.
- When called anywhere other than after final smooth, KRT explicitly owns
  ordering and subsequent result use.

## Result and data ownership

The call returns `GlossOutcome` with KRT objects to remove, structured changes,
and statistics. It may extend `results` and update `pcb_data` following the
same integration model as KRT stages.

A dgloss error restores entry state. No function in this API creates a User
layer or depends on `pcbnew`.

`stats` includes final G5 certification: validity, checked segment/via counts,
geometry-preserving re-emissions, and certification time. G5 does not modify
G4 routing.

## Compatibility requirements

- Keep `run_post_smooth_gloss` in `dgloss.__all__`.
- Use KRT types rather than dgloss copies.
- Add parameters only as backward-compatible named options.
- Keep `seed_segments=None` as historical complete-net behavior.
- Never require the plugin or CLI to use the API.
- Test import and execution without `pcbnew`.
