# KiCad KRGloss

KiCad KRGloss shortens, simplifies and centres tracks on an already routed
PCB. KRT remains responsible for obstacle, clearance and connectivity checks.

![A routed detour replaced by a shorter connection.](docs/assets/gloss-before-after.png)

## Install

In KiCad, open **Plugin and Content Manager**, choose **Install from File…**,
select the plugin ZIP, then open **PCB Editor → Tools → External Plugins →
KiCad KRGloss**.

## Choose the scope

<table>
<tr>
<td width="58%"><img src="docs/assets/dialog-general.png" alt="General tab with the net list and elementary-branch scope"></td>
<td>
<ol>
<li>Check the nets to process.</li>
<li>Click a row to highlight its remembered scope in KiCad.</li>
<li>Use <strong>Add</strong> or <strong>Replace</strong> to import the current
KiCad selection; <strong>Clear</strong> empties the list.</li>
</ol>
<p>With <strong>Use elementary branches</strong> enabled, a selected track
imports its complete branch up to pads, free ends or junctions. A row showing
<code>n EB</code> contains remembered branches; an empty EB cell means the
whole net. Disable the option to always process complete nets.</p>
</td>
</tr>
</table>

If nothing is selected in KiCad, the dialog opens with no checked net. The
action buttons remain disabled until at least one net is checked.

## Gloss

<table>
<tr>
<td width="58%"><img src="docs/assets/dialog-gloss.png" alt="Gloss tab"></td>
<td>
<ul>
<li><strong>Stay in corridor</strong> prevents a movement from crossing or
jumping over an obstacle.</li>
<li><strong>Movable vias</strong> allows eligible unlocked vias to move.</li>
<li><strong>Repeat Gloss until stable</strong> requests additional passes, up
to the displayed G4 limit.</li>
</ul>
<p>Click <strong>Gloss</strong>. A valid route may remain unchanged when no safe
improvement exists.</p>
</td>
</tr>
</table>

## Centering and Proximity max

<table>
<tr>
<td width="58%"><img src="docs/assets/dialog-centering.png" alt="Centering tab with Proximity max"></td>
<td>
<p>To set <strong>Proximity max</strong> from the board:</p>
<ol>
<li>In KiCad, select <strong>exactly two pads</strong>.</li>
<li>Open the <strong>Centering</strong> tab.</li>
<li>Click <strong>Refresh</strong>.</li>
<li>Check the centre-to-centre distance displayed in
<strong>Proximity max</strong>.</li>
<li>Check the target net and click <strong>Centering</strong>.</li>
</ol>
<p>The two-pad selection is used only to measure Proximity max. The checked net
or remembered elementary branches define which track is processed.</p>
</td>
</tr>
</table>

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
