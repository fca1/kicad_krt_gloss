# KiCad KRGloss 0.1.4 — testing release

Prepared 12 October 2026; publication and interactive acceptance remain to be
confirmed. Requires KiCad 10.x with the SWIG runtime. The installed action is
named **KiCad KRT Gloss**.

## Included changes

- Gloss is the sole action. General, Gloss, Log and About provide whole-net
  selection or remembered elementary branches through Add/Replace.
- Improved width transitions, pad-start recognition and final slide refinement.
  Refined slides also check coordinates rounded to KiCad's nanometre precision.
- Reduced unnecessary searches, delayed KRT raster construction and indexed
  nearby same-net geometry. KRT remains the authority for clearance and
  connectivity, with unchanged upstream sources.
- Optional corridor checks and movable vias. Additional G4 passes have their
  own pass limit; the initial time budget is not a total runtime ceiling.

KRT reports version 0.23.0, with sources pinned to
`9577628635e3de81d2c1fd8ac882254c0fa7d032` and official release binaries.
Windows x86-64, Linux x86-64 and macOS Intel/Apple Silicon binaries are packaged.

## Validation and limits

The latest recorded audit passed 361 targeted tests. The spatial-filter
comparison preserved exact geometry and non-timing statistics across 13
configurations, with G5 valid. Cumulative PACK0 runtime fell by 19.3% without
corridor and 25.8% with corridor relative to `8121a1d`. These figures compare
the last optimization step, not releases 0.1.3 and 0.1.4; no speedup on every
board is promised.

The local Windows installation from `d1897cb` passed native loading and
multiple-branch checks on a detached board. Its 274 packaged files were
verified and the source board remained unchanged. Interactive acceptance in
PCB Editor remains unrecorded. No Linux/macOS installation validation is claimed.

A known adversarial perpendicular via-sweep crossing case remains xfail in
KRT's predicate. G5 is not a complete KiCad DRC. Inspect changed copper,
especially moved vias, and run KiCad DRC before fabrication. Existing wxWidgets
warnings and KiCad 10's possible modified-board flag on opening an ActionPlugin
remain documented. Experimental audit prototypes are not included.

Install the release ZIP through Plugin and Content Manager → Install from
File, restart PCB Editor and first test on a copy of a board. This remains a
testing release.

Evidence in the source repository:

- [Geometry improvements](reports/GLOSS_FUSION_2026_10_12.md)
- [Spatial-filter validation](reports/GLOSS_SPATIAL_FILTERS_2026_10_12.md)
- [Follow-up audit](reports/GLOSS_FOLLOWUP_AUDIT_2026_10_12.md)
- [Local deployment](reports/GLOSS_DEPLOYMENT_2026_10_12.md)

When copying these notes into the publication kit or GitHub release, resolve
the report links against the published source revision: the kit does not
include historical reports.

Author and maintainer: Frantz, with assistance from ChatGPT/Codex (OpenAI).
KRT by DrAndyHaas. MIT licence; upstream notices retained.
