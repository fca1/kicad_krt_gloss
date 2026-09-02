# KiCad KRT Gloss

KiCad KRT Gloss improves an already routed PCB by shortening tracks, refining
movable vias and track-to-pad connections, simplifying junctions, and repeating
the enabled operations until no further useful improvement is found or the time
budget expires. Connectivity, clearances and the original routing intent are
preserved.

The project is built on
[KiCad Routing Tools (KRT)](https://github.com/drandyhaas/KiCadRoutingTools)
and reuses its grid, PCB parser, obstacle maps, clearance checks, connectivity
checks and output writer.

## KiCad plugin

Install the plugin ZIP with KiCad's Plugin and Content Manager. In the PCB
Editor, optionally select tracks, vias, pads, footprints or zones, then run
**KiCad KRT Gloss**:

- if objects are selected, their complete nets are processed;
- if nothing is selected, every routed net is processed.

The dialog lets you enable or disable mobile-via optimization, pad-terminal
optimization, sliding T-junctions, non-collinear T rails, complete via-chain
optimization and multi-net convergence passes. It also sets the KRT grid step
used by the standalone plugin. Every control has a short tooltip explaining
its purpose.

When `User.1` is free, the plugin names it **TrackGloss Changes** and displays
the final difference: old copper is dashed, new copper is solid, and moved vias
show their old and new positions. This is a visual aid only. If `User.1` is
already occupied, the gloss still runs and changes the copper, but the overlay
is not created. User layers are not included in Gerber output unless the user
explicitly adds them to a plot job.

## Command line

The CLI accepts the same net names, wildcard patterns, component filters and
placement groups as KRT:

```text
python gloss.py input.kicad_pcb output.kicad_pcb --nets "/Cpu/*"
python gloss.py input.kicad_pcb --component U1 --preview
python gloss.py input.kicad_pcb --json-out gloss-summary.json
```

Without a net selection, all routed nets are processed. The CLI writes the
glossed PCB and reports the length saved, changed nets, segment and via changes,
G4 pass count, G5 validation and elapsed time. `--preview` performs no file
write; `--json-out` writes the complete machine-readable report. The same
summary is also printed as `JSON_SUMMARY` and `JSON_SUMMARY_MIN`.

## Authors and license

The standalone adaptation was created and developed by **ChatGPT/Codex
(OpenAI)**. **Frantz** is co-author, project owner and maintainer.
**DrAndyHaas** is the author and primary code provenance of
[KiCad Routing Tools](https://github.com/drandyhaas/KiCadRoutingTools), used by
this project under the MIT License.

KiCad KRT Gloss is distributed under the [MIT License](LICENSE). Detailed
credits and retained notices are available in [AUTHORS.md](AUTHORS.md) and
[NOTICE](NOTICE).
