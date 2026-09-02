# KiCad KRT Gloss

Standalone final-gloss plugin built from the `dgloss` engine. KiCad Routing
Tools is consumed as the pinned `KRT` Git submodule and is not copied into this
repository.

```text
git clone --recurse-submodules <repository-url>
```

The repository intentionally keeps one branch, `main`. Milestones continue on
that branch through explicit commits and tags.

## Scope

- Selecting any tracks, vias, pads, footprints or copper zones identifies
  their complete nets.
- With no selected net, every routed net is processed.
- The standalone dialog controls G3.1 through G3.4, the optional
  non-collinear-T variant, G4 multi-pass convergence, and the grid step. Its
  default grid step is KRT's `0.1 mm` default.
- `dgloss.run_post_smooth_gloss()` remains public for a future direct KRT
  integration and uses the real `GridRouteConfig` supplied by KRT.

See `dgloss/doc/` for the specification, implementation notes, datasheet and
the separate KRT Python API contract.

## Authors, provenance and license

The standalone adaptation was created with ChatGPT/Codex (OpenAI). Frantz is
co-author and maintainer. The project consumes and reuses KiCad Routing Tools
under its retained MIT notices and preserves the copyright and primary code
provenance of DrAndyHaas. No algorithm from the earlier `kicad_gloss` (`kg`)
experiment is included.

See [AUTHORS.md](AUTHORS.md), [NOTICE](NOTICE) and [LICENSE](LICENSE).
