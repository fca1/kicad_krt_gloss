# Gloss and Centering

## Two actions, two goals

A routed track joins fixed points such as pads, vias, and junctions. It must
remain connected and respect required clearance from nearby copper.

| Action | Goal | Possible effect on length |
|---|---|---|
| Gloss | Shorten and simplify existing routing | Reduces it, or keeps it while removing an unnecessary detour |
| Centering | Place a track well in a passage | May keep it or increase it slightly |

Neither action freely redraws a connection. Both work on existing routed copper
and only in an allowed scope. Fixed items and protected areas are anchors or
obstacles and are never moved. Every change preserves connectivity, widths,
layers, required clearances, allowed routing directions, and obstacle avoidance.

## The admissible corridor

The admissible corridor is the set of positions an item can reach through a
continuous safe movement. Free start and end positions are not sufficient:
every intermediate position must also be valid. A track, via, or junction cannot
jump to the other side of an obstacle.

![A safe continuous route avoids obstacles, unlike the crossed-out direct route.](../../docs/assets/admissible-corridor.png)

## Gloss

Gloss searches for portions that can be shortened, then for equal-length shapes
using fewer segments. It reasons about relationships between neighbouring
segments, never about their on-screen orientation. Rotating or mirroring the
same shape must not change its treatment. Among valid candidates it prefers
useful length reduction, then fewer segments, then the simplest geometry.

![A detour is replaced by a direct connection.](../../docs/assets/gloss-before-after.png)

Gloss can remove local detours, merge aligned segments, shorten a track
approach, or locally move a via or junction when that mobility is allowed. A
gain too small to distinguish from the grid is rejected.

## Centering

Centering searches for **gates**: passages formed by two obstacles around a
track. It measures the actual available space on each side and places the track
as evenly as possible while keeping consistent margins. An isolated obstacle
does not define a gate. If the exact axis is impossible, it chooses the best
feasible centering; if no safe movement exists, the track stays put.

![An off-centre track is moved to the middle of its passage.](../../docs/assets/centering-before-after.png)

One branch can cross several gates. Centering can split a track into segments
that pass cleanly through their axes. This follows the passage between obstacles
rather than minimum length, so it can be slightly longer than Gloss alone.

## Action order and result

Centering is not a Gloss stage. When both are requested, Gloss first improves
the track while staying in its admissible corridor, Centering then places it in
the detected gates, and no later geometric transformation is applied.

The result may be shorter, simpler, better centred, or unchanged when no
improvement obeys every rule. No change is normal and means the existing
geometry is already the best safe solution in the examined scope.
