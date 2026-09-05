# Track Gloss — executable work specification

This document translates the functional specification in
[`gloss_rules.md`](gloss_rules.md) into architecture, stages, and technical
responsibilities. `gloss_rules.md` remains authoritative: any discrepancy must
be corrected here rather than by weakening the specification.

## Implementation principles

- Treat KRT as a library and write as little code as possible.
- The received routing, KiCad rules, and KRT checks are authoritative.
- Do not change Rust, KRT algorithms, or upstream grid construction without
  explicit approval.
- Reuse KRT types, geometry, length calculation, connectivity, rules, and
  obstacle checks.
- Work at the actual KRT grid resolution, with no arbitrary micron search or
  independent resolution.
- Accept only a gain strictly greater than the useful grid step.

## Post-smooth integration

Two entry points are separate:

1. `run_final_gloss()` is the plugin adapter. It requests KRT's final
   `smooth_octolinear_chains()` and passes that result to the gloss.
2. `run_post_smooth_gloss()` receives an already smoothed result and never
   reruns smooth. It remains a public KRT-compatible Python API so KRT may call
   dgloss after its final smooth or integrate it more closely later.

The second contract is detailed in
[`gloss_krt_python_api.md`](gloss_krt_python_api.md) and is independent of the
CLI.

The gloss runs once, after all intermediate smooth operations and final
reconciliation. G0 resolves selection and exclusions once, then
`build_gloss_context()` rebuilds the required layers, caches, obstacles, and
grids from final copper with KRT constructors. KRT-protected nets and arc nets
are excluded from modification but remain obstacles. A locked via protects its
whole net according to KRT policy.

The same `GlossContext` is passed through the entire pipeline and G4. Later
updates replace only the cache of the changed net; they do not rebuild the grid
or obstacle base. G3.x modules provide only their internal geometry searches:
they no longer resolve selection or recalculate protected-net lists.
`KrtClearanceAdapter` is a thin adapter to KRT checks, not a parallel clearance
engine.

### Elementary-branch scope

When segment seeds are supplied, G0 builds their union of elementary branches
once from final KRT topology. Traversal stops at pads, free ends, and junctions,
using KRT pad geometry and via-span primitives. The complete net remains
present for obstacles and connectivity checks.

The context carries the identities of editable segments. Each accepted
replacement removes old identities and adds new ones. G3 through G3.5 filter
against this shared set instead of rediscovering the branch. Final smooth and
collinear merge remain KRT functions: a temporary result limited to the active
branch drives their `keep_input_copper` option, then the adapter reconciles
their additions and removals with the real result. No KRT or Rust change is
required.

At a T with a collinear rail, the selected branch may move its connection along
the rail because rail copper remains geometrically unchanged. The non-collinear
variant is attempted only when every branch it would rewrite is editable.

The foreign-obstacle view is also unique for the run. It is cloned once from
the persistent KRT grid, then switches excluded nets through KRT batch add and
remove operations. A changed net's recomputed cache replaces its previous
cache in both persistent and reusable views. This avoids a deep grid copy for
every stage/net pair without changing observable obstacles or clearance rules.

## Stage breakdown

### G0 — transparent integration

Connect the gloss after final smooth, rebuild its context from the final
result, and return identical output when no transformation is made. No special
core behavior is introduced for an empty net selection.

### G1 — visualization

Show changes only: old copper dashed, new copper solid, and old/new positions
of moved vias. Visualization is downstream and can neither permit nor reject a
transformation. It belongs solely to the plugin adapter: dgloss knows neither
`pcbnew` nor User layers. `add_layer_user()` enables and names a free User layer
without overwriting an occupied layer.

### G2 — removed integration experiment

Temporary track widening only validated data exchange, obstacles, and return
to KiCad. Its algorithm and special clearance reconstruction were removed and
must not be used as a gloss foundation.

### G3 — ordinary-chain reduction

Reduce length net by net, with fixed vias, by walking simple chains. A diagonal
connection may slide along adjacent segments at the KRT grid step. Search starts
from existing geometry in jumps of five KRT cells. At the first obstacle
confirmed by exact KRT checking, it returns to the last interval and refines
cell by cell. A family is abandoned when its first jump is genuinely blocked.
The selected candidate is compared with the existing chain, checked by KRT,
and connectivity-checked before application.

### G3.1 — local mobile vias

Allow vias meeting the four mobility conditions and optimize their two
incident legs without changing their attributes.

### G3.2 — pad terminations

Optimize the terminal chain to the pad's fixed native point. KRT checks handle
same-net pad status directly; no manual carving around the pad is added.

### G3.3 — sliding T junctions and nodes

Identify a collinear rail, preserve it, and search its grid positions for the
best branch connection. The connection may meet the rail at 90 degrees. The
default `enable_noncollinear_t_rails` option also tries each segment of a T
without a collinear rail as the mobile branch and atomically removes any
parasitic 90-degree bend left at the old node.

### G3.4 — vias and complete chains

Reuse G3.1 while extending evaluation to both complete portions articulated by
the mobile via. The KRT Rust grid first rejects clearly blocked connections.
Survivors still undergo KRT exact geometry checking; the grid filter is never
sufficient certification.

### G3.5 — complete coordination

Run G3 followed by configuration-enabled G3.1 through G3.4 under one budget.
Then complete the lexicographic segment-count objective: rerun G3 in
"equal length, fewer segments" mode with KRT canonical connectors only, and use
KRT `merge_collinear_segments()` to merge strict alignments without moving
copper.

A common final certification checks non-increasing length, connectivity of all
nets, octilinear geometry, and that no segment created by a geometric
transformation is shorter than the real grid step. A geometry-preserving KRT
re-emission is not treated as new copper. On failure, restore the exact KRT
result.

G3.5 aggregates `GlossStats`, keeps the KRT smooth gain separate from the
dgloss gain, and produces one cumulative debug view without duplicated copper.

### G4 — convergence passes

When `enable_multipasses` is enabled, G4 calls the complete G3.5 pipeline once
per pass with the full net list. An empty list means all nets. Deterministic
order alternates ascending and descending; an accepted result is immediately
visible to the next net. Passes stop after the first complete pass without a
transformation or when the global budget expires. G4 owns no geometry
algorithm; it only orchestrates G3.5 and its options.

G4 calls private `_run_g3_5_pass()` once per pass with the complete ordered
list and the single `GlossContext` prepared by G0. It calls neither public G0
nor `build_gloss_context()` again. Only a changed net's obstacle cache is
replaced. Errors propagate so G0 can atomically restore the complete gloss.

From G4 onward, one User layer shows the difference between gloss input and
final output.

### G5 — compliance certification

G5 creates no geometry. After G4 it reuses the KRT connectivity graph to verify
that each net's pad/zone partition is strictly unchanged. It then revalidates
every actually moved final segment and mobile via through the KRT rule adapter.

A mobile via's dimensions, layers, net, lock state, and manufacturing
attributes are compared before and after. Segments merely re-emitted by KRT's
collinear merge are marked geometry-preserving and are not mistaken for moved
copper. Any failure triggers G0's atomic rollback.

## Modules and responsibilities

| Module | Responsibility |
|---|---|
| `pipeline.py` | G0 entry, G3.5 core, G5 certification, rollback |
| `branches.py` | One-time elementary-branch resolution from seeds |
| `context.py` | KRT grid-context reconstruction |
| `krt_clearance.py` | Thin adapter to KRT checks |
| `algorithm.py` | G3 ordinary chains |
| `via_mobile.py` | G3.1 and G3.4 |
| `pad_terminals.py` | G3.2 |
| `sliding_nodes.py` | G3.3 |
| `config.py` | dgloss-owned options |
| `stats.py` | Structured statistics and log lines |
| `passes.py` | G4 deterministic multinet repetition of G3.5 |
| `gloss.py` | Standalone KRT-compatible CLI selection and output |
| `kicad_krt_gloss/board_adapter.py` | `pcbnew` adapter between the live PCB and KRT types |
| `kicad_krt_gloss/gloss_visualization.py` | User layer and final before/after rendering |

## Validation and traceability

Each stage produces testable output and then a matching commit and tag.
Historical reports live in `docs/reports/`. Targeted tests cover
transformations, invariants, disabled options, the budget, and the absence of a
second smooth in the post-smooth entry point.
