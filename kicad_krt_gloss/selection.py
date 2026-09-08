"""Convert native KiCad selections to KRT-oriented selection data."""

from collections import defaultdict
import math


POSITION_DECIMALS = 6


def highlight_net_names(board, names):
    """Highlight nets through native flags and report the native active state."""
    import pcbnew
    chosen = set(names)
    codes = [code for code, net in board.GetNetsByNetcode().items()
             if code > 0 and net.GetNetname() in chosen]
    board.ResetNetHighLight()
    for code in codes:
        board.SetHighLightNet(code, True)
    board.HighLightON(bool(codes))
    pcbnew.Refresh()
    update_ui = getattr(pcbnew, "UpdateUserInterface", None)
    if callable(update_ui):
        update_ui()
    active = bool(board.IsHighLightNetON())
    return (not chosen and not active) or (bool(codes) and active)


def selected_pad_pair_distance_mm(board):
    """Return the centre spacing of an exclusive two-pad selection in mm.

    ``None`` deliberately covers every other selection shape.  The plugin uses
    this only as a UI shortcut: it must not turn selected copper, a footprint,
    or another board item into an implicit Centering request.
    """
    selected = getattr(board, "GetSelectedItems", None)
    if callable(selected):
        try:
            items = list(selected())
        except (AttributeError, TypeError):
            items = None
        if items is not None:
            pads = [item for item in items
                    if getattr(item, "GetClass", lambda: "")() == "PCB_PAD"]
            return _pad_pair_distance_mm(pads) if len(items) == len(pads) else None

    # KiCad versions without BOARD.GetSelectedItems need a conservative
    # fallback.  It covers pads and the other selectable board collections.
    pads = [pad for footprint in board.GetFootprints()
            for pad in footprint.Pads() if pad.IsSelected()]
    others = [item for item in board.GetTracks() if item.IsSelected()]
    others.extend(footprint for footprint in board.GetFootprints()
                  if footprint.IsSelected())
    for getter in ("GetDrawings", "Zones"):
        collection = getattr(board, getter, None)
        if callable(collection):
            others.extend(item for item in collection() if item.IsSelected())
    return _pad_pair_distance_mm(pads) if not others else None


def _pad_pair_distance_mm(pads):
    if len(pads) != 2:
        return None
    try:
        first, second = (pad.GetPosition() for pad in pads)
        import pcbnew
        dx = float(pcbnew.ToMM(first.x) - pcbnew.ToMM(second.x))
        dy = float(pcbnew.ToMM(first.y) - pcbnew.ToMM(second.y))
    except (AttributeError, TypeError, ValueError):
        return None
    return math.hypot(dx, dy)


def selected_net_ids(board):
    """Return nets designated by one or more selected straight segments."""
    net_ids = set()
    for item in board.GetTracks():
        try:
            if not item.IsSelected() or item.GetClass() != "PCB_TRACK":
                continue
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
