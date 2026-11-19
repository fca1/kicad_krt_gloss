# KiCad KRGloss

KiCad KRGloss reduces and simplifies one or more already routed tracks, most
often after autorouting or manual routing. It is built on KiCad Routing Tools
by DrAndyHaas, which provides obstacle, clearance and connectivity checks.

![KiCad PCB Editor: the TrackGloss Changes overlay on User.1 shows the former dotted detour and the final shortened track.](docs/assets/kicad-user1-reductions.png)

This KiCad capture uses a medium board and runs Gloss only on the small
`D10~` track set. In the **Appearance** panel, the active copper layers and
**TrackGloss Changes** on `User.1` are visible together: the solid red routing
is the result, while the dotted overlay preserves the former path for review.

## Install

The development version **0.1.5** uses **IPC** and KRT **0.24.1**. It targets
KiCad **10.99 / 11** with the live design-rule API. Windows 10.99 is the local
test platform; Linux and macOS execution has not been validated.

Place the staged plugin contents in the KiCad version's `plugins/` directory,
enable the KiCad API server, and launch **KRT Gloss** from the PCB toolbar.
KiCad installs the Python dependencies from `requirements.txt`. Restart PCB
Editor after installation and first test on a copy of your board. See the
[IPC installation and limitations](docs/IPC.md). No 0.1.5 release is published yet.

## Choose the scope

**Check** a net to include it. IPC mode does not highlight nets or branches.
**Add / Replace** imports the KiCad selection; **Clear** empties the list.

With **Use elementary branches** enabled, importing a selected track remembers
its full branch, bounded by pads, free ends or junctions. **n EB** means partial
branch scope; a blank EB cell means the whole net. Without remembered branches,
checking a net selects the whole net.

If nothing is selected in KiCad, the dialog opens with no checked net. The
Gloss button remains disabled until at least one net is checked.

## Gloss

- **Stay in corridor** requires a continuous admissible movement; it is off
  by default.
- **Movable vias** allows eligible unlocked vias to move.
- **Repeat Gloss until stable** adds passes up to the G4 limit.

The G4 limit is 1–10 additional passes (1 by default). These passes are
additional to the initial time budget.

Click **Gloss**. No change is normal when no safe improvement exists.

## Review the result

The **Log** tab records the options, net names and result. The plugin also
adds a **KRT Gloss changes (IPC)** group on a free enabled User layer when one
is available: old copper is dashed and new copper is solid. This is a visual aid, not a replacement
for KiCad's visual inspection and DRC.

A known limitation remains in KRT's perpendicular via-sweep crossing check.
Review moved vias and run KiCad DRC before fabrication; G5 is not a full DRC.

Gloss modifies existing routing only. Locked or protected copper,
arcs, differential pairs and constrained tracks remain protected.

## Author and licence

**Frantz** is the author, project owner and maintainer. The project was
developed with assistance from **ChatGPT/Codex (OpenAI)**.

**DrAndyHaas** is the author and primary code provenance of
[KiCad Routing Tools (KRT)](https://github.com/drandyhaas/KiCadRoutingTools).
The Gloss sources retain their [MIT License](LICENSE). The IPC distribution
also includes KiCad protocol definitions under GPL-3.0-or-later and protobuf
definitions under their BSD license; see `IPC_PROTOCOL_NOTICE.txt` and the
included license texts. Detailed provenance is recorded in
[AUTHORS.md](docs/AUTHORS.md) and [NOTICE](NOTICE).
