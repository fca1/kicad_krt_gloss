# KiCad KRT Gloss

KiCad KRT Gloss improves an already routed PCB by shortening tracks, refining
movable vias and track-to-pad connections, simplifying junctions, and repeating
the enabled operations until their stopping conditions are met. The initial
budget is not a total runtime limit: G4 may continue beyond it.
Connectivity, clearances and the original routing intent are
preserved.

The project is built on
[KiCad Routing Tools (KRT)](https://github.com/drandyhaas/KiCadRoutingTools)
and reuses its grid, PCB parser, obstacle maps, clearance checks, connectivity
checks and output writer.

## KiCad plugin

Install the plugin ZIP with KiCad's Plugin and Content Manager. In the PCB
Editor, optionally select tracks, vias, pads, footprints or zones, then run
**KiCad KRT Gloss**:

- by default, each selected straight track is a seed and only its complete
  elementary branch, up to the next pad, free end or junction, is processed;
- the first dialog option can instead make the selection process complete nets;
- if no straight track is selected, other selected objects continue to select
  complete nets;
- if nothing is selected, the dialog opens with no checked nets; both actions
  remain disabled until nets are checked.

The dialog opens when zero or more than one net is selected; an exact one-net
selection runs immediately with the remembered settings. It reports the
selected net count. General contains the shared net list, component filters,
EB (elementary branches), grid step and budget. Gloss contains movable vias,
Stay in corridor and G4 controls; Centering contains Proxi.
With EB enabled, Add unions imported KiCad branches and Replace replaces the
remembered scope; Clear unchecks all nets. A net without remembered branches
means the whole net. Partial scope shows `n EB`; whole-net scope is blank.
Complete branch coverage becomes whole-net scope. Reimport stale branches
after their tracks have been replaced. Clicking a row previews its remembered
scope; checking it includes that scope in Gloss or Centering.
Centering runs corridor Gloss followed by Centering atomically, with no
geometry transformation afterwards. Proxi bounds pad centre-to-centre distance.
Its **Log** tab retains the latest stage statistics and final result; **Clear
Log** removes that history. The bottom buttons are **Gloss**, **Centering** and
**Close**; the dialog remains available after a run.

The plugin and CLI gloss the routing state they receive; neither implicitly
runs KRT's `smooth_octolinear_chains()`. KRT may instead call the documented
post-smooth API after its own final smooth.

The plugin reuses its existing **TrackGloss Changes** layer or selects the first
free `User.N` layer in ascending order. It displays the final difference: old
copper is dashed, new copper is solid (0.1 mm display width in the plugin), and moved vias show their old and new
positions. It never overwrites a user-owned layer. This is a visual aid only;
User layers are not included in Gerber output unless the user explicitly adds
them to a plot job.

## Command line

The CLI accepts the same net names, wildcard patterns, component filters and
placement groups as KRT:

```text
python gloss.py input.kicad_pcb output.kicad_pcb --nets "/Cpu/*"
python gloss.py input.kicad_pcb --component U1 --preview
python gloss.py input.kicad_pcb --nets "/A" --stay-in-corridor --preview
python gloss.py input.kicad_pcb --json-out gloss-summary.json
python gloss.py input.kicad_pcb --debug-layer auto
```

The CLI deliberately selects whole nets only. Never expose EB/branch selection
as a CLI option: it belongs exclusively to the KiCad dialog. The current CLI
runs Gloss, not Centering, and has no Proxi option. It uses the current shared
Gloss engine, but does not expose every dialog control (notably the G4 pass limit).
`--stay-in-corridor` enables the admissible routing corridor for Gloss.

Without a net selection, all routed nets are processed (unlike the dialog).
The CLI writes the
glossed PCB and reports the length saved, changed nets, segment and via changes,
G4 pass count, G5 validation and elapsed time. `--preview` performs no file
PCB write; `--json-out` can still write the machine-readable report. The same
summary is also printed as `JSON_SUMMARY` and `JSON_SUMMARY_MIN`.
`--debug-layer auto` writes a final before/after overlay on the first
free User layer; `--debug-layer User.N` requests a specific free layer.

## Authors and license

The standalone adaptation was created and developed by **ChatGPT/Codex
(OpenAI)**. **Frantz** is co-author, project owner and maintainer.
**DrAndyHaas** is the author and primary code provenance of
[KiCad Routing Tools](https://github.com/drandyhaas/KiCadRoutingTools), used by
this project under the MIT License.

KiCad KRT Gloss is distributed under the [MIT License](LICENSE). Detailed
credits and retained notices are available in [AUTHORS.md](docs/AUTHORS.md) and
[NOTICE](NOTICE).
