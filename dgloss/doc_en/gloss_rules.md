# Track Gloss — reference specification

## Purpose

Track Gloss is a final treatment of an existing route. It seeks shorter
geometry without autorouting and without changing the design beyond this final
treatment.

The mandatory order of objectives is:

1. respect the input data and every applicable rule;
2. at equivalent geometry, reduce the segment count;
3. keep an exclusively octilinear output: 0, 45, or 90 degrees;
4. create no micro-segment, jog, or unnecessary detour.

## Definition

- A seed is a KRT segment explicitly designated as the starting point of a
  transformation.
- An elementary branch is the maximal unbranched path containing its seed. It
  ends at a pad, free end, or T/X junction. It continues through a width or
  layer change and through a via that is not itself a branch point.
- A fixed, locked, or protected element keeps its position, geometry, and
  attributes. It may serve as an anchor or obstacle, but no gloss stage may
  move, replace, or modify it. Mobility is allowed only when a rule explicitly
  provides for it and all its conditions are met.

## Exclusion

Before any transformation, the following nets are excluded in full from the
modifiable scope:

1. length- or timing-constrained groups;
2. coupled differential pairs;
3. impedance-constrained nets;
4. nets containing locked copper, whether track or via;
5. nets containing arcs.

These exclusions remain obstacles for other nets. Explicit selection does not
override their protection.

## Scope

- The gloss processes one or more explicitly designated elementary branches.
- Outside the scope, the remainder of the net is preserved and participates in
  the same topology and obstacle checks as copper from other nets.
- A connection is considered from fixed pad to fixed pad and remains continuous
  through its vias.
- Only copper belonging to the connection under examination may be changed;
  every other copper item remains an obstacle.
- A width change alone does not terminate or split a connection.
- A track receives no implicit protection from its apparent purpose.

## Fixed points and topology

### Pads

The native pad landing point, usually its center, is fixed. A track may not
arbitrarily choose another point on the pad edge. The final pad connection
remains octilinear.

### Vias

A fixed via is an articulation crossed by the connection, not a termination. A
via may be mobile only when all four conditions below hold:

1. exactly two segments of the same net are incident to it;
2. those segments belong to two different copper layers;
3. both sides belong entirely to the modifiable scope;
4. no native constraint fixes its position.

When a via is mobile, its diameter, drill, type, net, and layer span remain
unchanged. Its initial position remains a valid fallback solution.

### T junctions and nodes

In a T made of two collinear segments forming a rail and one branch, the branch
connection may move along the rail without moving the rail itself. The branch
may be perpendicular to the rail: this 90-degree angle is allowed and may be
the minimum-length solution. It must not be confused with a parasitic
90-degree bend at the other end of the branch.

An optional variant may handle a T without a collinear pair: each of the three
segments is considered in turn as the branch, with the other two as possible
rails. After the move, any parasitic 90-degree bend left at the old node is
simplified according to the general gloss rules. When this variant is disabled,
a node without a collinear pair remains fixed. Fixed pads and vias take
precedence over junction mobility.
