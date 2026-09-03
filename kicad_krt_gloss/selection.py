"""Convert the live KiCad selection to complete KRT net identifiers."""


def selected_net_ids(board):
    """Return sorted unique positive net codes from every selectable PCB item."""
    selected = []
    selected.extend(item for item in board.GetTracks() if item.IsSelected())

    for footprint in board.GetFootprints():
        footprint_selected = footprint.IsSelected()
        selected.extend(pad for pad in footprint.Pads()
                        if footprint_selected or pad.IsSelected())

    try:
        selected.extend(board.GetArea(index)
                        for index in range(board.GetAreaCount())
                        if board.GetArea(index).IsSelected())
    except AttributeError:
        selected.extend(zone for zone in board.Zones() if zone.IsSelected())

    net_ids = set()
    for item in selected:
        try:
            net_id = int(item.GetNetCode())
        except (AttributeError, TypeError, ValueError):
            continue
        if net_id > 0:
            net_ids.add(net_id)
    return sorted(net_ids)


def native_arc_net_ids(board):
    """Return nets whose native arc tracks cannot be rewritten as KRT chords."""
    net_ids = set()
    for item in board.GetTracks():
        try:
            is_arc = item.GetClass() == "PCB_ARC"
        except AttributeError:
            is_arc = False
        if is_arc:
            net_id = int(item.GetNetCode())
            if net_id > 0:
                net_ids.add(net_id)
    return sorted(net_ids)
