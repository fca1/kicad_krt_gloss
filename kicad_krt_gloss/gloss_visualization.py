"""KiCad/pcbnew adapter for rendering dgloss changes on User layers.

This module deliberately lives in the plugin.  The dgloss engine only emits
plain structured changes and therefore remains importable without pcbnew.
"""

import math


LAYER_NAME = "TrackGloss Changes"
STAGE_LAYERS = {"G3": 1, "G3.1": 2, "G3.2": 3,
                "G3.3": 4, "G3.4": 5, "G3.5": 6, "G4": 1}
INTERMEDIATE_LAYER_NAMES = {
    2: "TrackGloss G3.1", 3: "TrackGloss G3.2",
    4: "TrackGloss G3.3", 5: "TrackGloss G3.4",
    6: "TrackGloss G3.5",
}


def _line_parts(start, end, dash=0.30, gap=0.20):
    """Return short line parts forming a visible dashed segment."""
    x1, y1 = start
    x2, y2 = end
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 1e-12:
        return []
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    parts = []
    pos = 0.0
    while pos < length:
        stop = min(length, pos + dash)
        parts.append(((x1 + ux * pos, y1 + uy * pos),
                      (x1 + ux * stop, y1 + uy * stop)))
        pos += dash + gap
    return parts


def _disable_layer(layer_set, layer_id):
    """Remove one layer from a KiCad LSET without deleting board objects."""
    if not layer_set.Contains(layer_id):
        return False
    for name in ("RemoveLayer", "removeLayer"):
        method = getattr(layer_set, name, None)
        if method is not None:
            method(layer_id)
            return True
    return False


def disable_intermediate_layers(board, pcbnew):
    """Disable legacy dgloss User.2--User.6 layers; preserve their drawings."""
    enabled = board.GetEnabledLayers()
    visible = board.GetVisibleLayers()
    enabled_changed = visible_changed = False
    for index, expected_name in INTERMEDIATE_LAYER_NAMES.items():
        layer_id = getattr(pcbnew, f"User_{index}", None)
        if layer_id is None or board.GetLayerName(layer_id) != expected_name:
            continue
        enabled_changed = _disable_layer(enabled, layer_id) or enabled_changed
        visible_changed = _disable_layer(visible, layer_id) or visible_changed
    if enabled_changed:
        board.SetEnabledLayers(enabled)
    if visible_changed:
        board.SetVisibleLayers(visible)


def add_layer_user(board, pcbnew, stage="G3"):
    """Create/enable the stage's User layer without taking over user content."""
    index = STAGE_LAYERS.get(stage, 1)
    layer_id = getattr(pcbnew, f"User_{index}", None)
    if layer_id is None:
        return None
    name = LAYER_NAME if stage == "G4" else f"TrackGloss {stage}"
    occupied = {item.GetLayer() for item in board.GetDrawings()}
    current_name = board.GetLayerName(layer_id)
    if layer_id in occupied and current_name != name:
        print(f"Track Gloss: User.{index} is occupied; {stage} overlay skipped")
        return None

    try:
        if board.GetUserDefinedLayerCount() < index:
            board.SetUserDefinedLayerCount(index)
    except AttributeError:
        pass
    enabled = board.GetEnabledLayers()
    if not enabled.Contains(layer_id):
        try:
            enabled.AddLayer(layer_id)
        except AttributeError:
            enabled.addLayer(layer_id)
        board.SetEnabledLayers(enabled)
    board.SetLayerName(layer_id, name)
    try:
        visible = board.GetVisibleLayers()
        if not visible.Contains(layer_id):
            try:
                visible.AddLayer(layer_id)
            except AttributeError:
                visible.addLayer(layer_id)
            board.SetVisibleLayers(visible)
    except AttributeError:
        pass
    return layer_id


def add_changes_to_board(board, changes, stage="G3"):
    """Render changed copper only; leave the board untouched for an empty log."""
    segments = changes.get("segments") or []
    vias = changes.get("vias") or []
    if not segments and not vias:
        return 0

    import pcbnew
    from kicad_parser import mm_to_iu

    layer_id = add_layer_user(board, pcbnew, stage=stage)
    if layer_id is None:
        return 0
    for item in list(board.GetDrawings()):
        if item.GetLayer() == layer_id:
            board.RemoveNative(item)
    count = 0

    def add_line(start, end, width):
        nonlocal count
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(pcbnew.VECTOR2I(mm_to_iu(start[0]), mm_to_iu(start[1])))
        shape.SetEnd(pcbnew.VECTOR2I(mm_to_iu(end[0]), mm_to_iu(end[1])))
        shape.SetWidth(mm_to_iu(max(0.03, width)))
        shape.SetLayer(layer_id)
        board.Add(shape)
        count += 1

    # New copper first; old dashed copper keeps the former route readable.
    for change in segments:
        new = change.get("new")
        if new is None:
            continue
        add_line((new.start_x, new.start_y), (new.end_x, new.end_y), new.width)
    for change in segments:
        old = change.get("old")
        if old is None:
            continue
        for start, end in _line_parts(
                (old.start_x, old.start_y), (old.end_x, old.end_y)):
            add_line(start, end, min(old.width, 0.10))

    for change in vias:
        old, new = change["old"], change["new"]
        radius = max(getattr(new, "size", 0.3) / 2.0, 0.15)
        for via, dashed in ((new, False), (old, True)):
            points = [(via.x + radius * math.cos(2 * math.pi * i / 20),
                       via.y + radius * math.sin(2 * math.pi * i / 20))
                      for i in range(21)]
            for i in range(20):
                if not dashed or i % 2 == 0:
                    add_line(points[i], points[i + 1], 0.05)
        add_line((old.x, old.y), (new.x, new.y), 0.05)
    board.SetModified()
    return count
