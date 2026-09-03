"""Convert the live KiCad selection to complete KRT net identifiers."""

from collections import defaultdict


POSITION_DECIMALS = 6


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


def selected_seed_segments(board, pcb_data):
    """Map selected native straight tracks to their KRT Segment objects."""
    import pcbnew

    def mm(value):
        return round(float(pcbnew.ToMM(value)), POSITION_DECIMALS)

    def native_key(track):
        a = (mm(track.GetStart().x), mm(track.GetStart().y))
        b = (mm(track.GetEnd().x), mm(track.GetEnd().y))
        return (frozenset((a, b)), board.GetLayerName(track.GetLayer()),
                int(track.GetNetCode()), mm(track.GetWidth()))

    def segment_key(segment):
        a = (round(segment.start_x, POSITION_DECIMALS),
             round(segment.start_y, POSITION_DECIMALS))
        b = (round(segment.end_x, POSITION_DECIMALS),
             round(segment.end_y, POSITION_DECIMALS))
        return (frozenset((a, b)), segment.layer, int(segment.net_id),
                round(float(segment.width), POSITION_DECIMALS))

    segments = defaultdict(list)
    for segment in pcb_data.segments:
        if not getattr(segment, "graphic", False):
            segments[segment_key(segment)].append(segment)

    selected = []
    for track in board.GetTracks():
        if not track.IsSelected() or track.GetClass() != "PCB_TRACK":
            continue
        bucket = segments.get(native_key(track))
        if bucket:
            selected.append(bucket.pop())
    return selected


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
