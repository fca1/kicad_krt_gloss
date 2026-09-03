"""KiCad/pcbnew adapter for rendering dgloss changes on User layers.

This module deliberately lives in the plugin.  The dgloss engine only emits
plain structured changes and therefore remains importable without pcbnew.
"""

from .debug_overlay import (LAYER_NAME, USER_LAYER_NAMES, choose_user_layer,
                            line_parts as _line_parts, overlay_lines)


INTERMEDIATE_LAYER_NAMES = {
    2: "TrackGloss G3.1", 3: "TrackGloss G3.2",
    4: "TrackGloss G3.3", 5: "TrackGloss G3.4",
    6: "TrackGloss G3.5",
}


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


def _occupied_user_layers(board):
    items = list(board.GetDrawings())
    for footprint in getattr(board, "GetFootprints", lambda: [])():
        items.extend(getattr(footprint, "GraphicalItems", lambda: [])())
    items.extend(getattr(board, "Zones", lambda: [])())
    return {item.GetLayer() for item in items}


def add_layer_user(board, pcbnew, stage="G4"):
    """Enable the owned layer, or claim the first genuinely free User layer."""
    del stage  # One final overlay since G4; retained for API compatibility.
    layer_ids = {
        name: getattr(pcbnew, f"User_{name.split('.')[1]}", None)
        for name in USER_LAYER_NAMES}
    layer_ids = {name: layer_id for name, layer_id in layer_ids.items()
                 if layer_id is not None}
    occupied_ids = _occupied_user_layers(board)
    display_names = {
        name: board.GetLayerName(layer_id) for name, layer_id in layer_ids.items()}
    occupied = {name for name, layer_id in layer_ids.items()
                if layer_id in occupied_ids}
    selected = choose_user_layer(display_names, occupied)
    if selected is None:
        print("Track Gloss: no free User layer; final overlay skipped")
        return None
    index = int(selected.split(".", 1)[1])
    layer_id = layer_ids[selected]

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
    board.SetLayerName(layer_id, LAYER_NAME)
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


def add_changes_to_board(board, changes, stage="G4"):
    """Replace the owned final overlay, including with an empty result."""
    import pcbnew

    segments = changes.get("segments") or []
    vias = changes.get("vias") or []
    if not segments and not vias:
        owned_ids = {
            getattr(pcbnew, f"User_{name.split('.')[1]}", None)
            for name in USER_LAYER_NAMES
            if getattr(pcbnew, f"User_{name.split('.')[1]}", None) is not None
            and board.GetLayerName(
                getattr(pcbnew, f"User_{name.split('.')[1]}")) == LAYER_NAME}
        removed = False
        for item in list(board.GetDrawings()):
            if item.GetLayer() in owned_ids:
                board.RemoveNative(item)
                removed = True
        if removed:
            board.SetModified()
        return 0

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

    for start, end, width in overlay_lines(changes):
        add_line(start, end, width)
    board.SetModified()
    return count
