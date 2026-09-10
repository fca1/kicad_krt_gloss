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

In KiCad, open **Plugin and Content Manager**, choose **Install from File…**,
select the plugin ZIP, then open **PCB Editor → Tools → External Plugins →
KiCad KRGloss**.

## Choose the scope

| General | Choose nets or branches |
| --- | --- |
| ![General: visible net names, 1 EB scope and action buttons.](docs/assets/dialog-general.png) | **Check** a net to include it; **click** a row to highlight its scope.<br><br>**Add / Replace** imports the KiCad selection. **Clear** empties the list.<br><br>With **Use elementary branches** enabled, importing a selected track remembers its full branch, bounded by pads, free ends or junctions. **n EB** means partial branch scope; a blank EB cell means the whole net. Without remembered branches, checking a net selects the whole net. |

If nothing is selected in KiCad, the dialog opens with no checked net. The
action buttons remain disabled until at least one net is checked.

## Gloss

| Gloss | Shorten and simplify |
| --- | --- |
| ![Gloss: corridor and via illustrations, settings and action buttons.](docs/assets/dialog-gloss.png) | **Stay in corridor** prevents crossing or jumping over an obstacle.<br><br>**Movable vias** allows eligible unlocked vias to move.<br><br>**Repeat Gloss until stable** adds passes up to the G4 limit.<br><br>Click **Gloss**. No change is normal when no safe improvement exists. |

## Centering and Proximity max

| Centering | Set Proxi using two pads |
| --- | --- |
| ![Centering: Proximity max 2.54 mm, illustration and Refresh button.](docs/assets/dialog-centering.png) | **1.** In KiCad, select **exactly two pads**.<br><br>**2.** Open the **Centering** tab and click **Refresh**.<br><br>**3.** Check the **centre-to-centre distance** shown in **Proximity max** (0–5 mm).<br><br>**4.** In General, check the target net or import its branches, then click **Centering**. |

The two-pad selection is used only to measure Proximity max. The checked net
or remembered elementary branches define which track is processed.

Proximity max is the largest pad centre-to-centre spacing accepted when
detecting a gate. Centering first runs a corridor-constrained Gloss, then moves
the track towards the middle of valid gates. No geometry transformation runs
after Centering.

## Review the result

The **Log** tab records the options, net names and result. The plugin also
creates or reuses **TrackGloss Changes** on a free User layer: old copper is
dashed and new copper is solid. This layer is a visual aid, not a replacement
for KiCad's visual inspection and DRC.

Gloss and Centering modify existing routing only. Locked or protected copper,
arcs, differential pairs and constrained tracks remain protected.

## Author and licence

**Frantz** is the author, project owner and maintainer. The project was
developed with assistance from **ChatGPT/Codex (OpenAI)**.

**DrAndyHaas** is the author and primary code provenance of
[KiCad Routing Tools (KRT)](https://github.com/drandyhaas/KiCadRoutingTools).
KiCad KRGloss is distributed under the [MIT License](LICENSE); detailed
provenance is recorded in [AUTHORS.md](docs/AUTHORS.md) and [NOTICE](NOTICE).
