"""Thin pcbnew boundary around KRT data and dgloss structured changes."""

from collections import defaultdict


POSITION_DECIMALS = 6


def _mm(pcbnew, value):
    return float(pcbnew.ToMM(value))


def build_krt_config(board, pcb_data, grid_step, net_ids=None):
    """Build GridRouteConfig from live native rules plus the standalone grid."""
    import pcbnew
    from routing_config import GridRouteConfig

    settings = board.GetDesignSettings()
    net_settings = getattr(settings, "m_NetSettings", None)
    default_class = None
    try:
        default_class = net_settings.GetDefaultNetclass()
    except Exception:
        pass

    def class_value(name, fallback):
        if default_class is None:
            return fallback
        try:
            value = _mm(pcbnew, getattr(default_class, name)())
            return value if value > 0 else fallback
        except Exception:
            return fallback

    edge = 0.0
    try:
        edge = _mm(pcbnew, settings.m_CopperEdgeClearance)
    except Exception:
        pass
    config = GridRouteConfig(
        track_width=class_value("GetTrackWidth", 0.1),
        clearance=class_value("GetClearance", 0.1),
        via_size=class_value("GetViaDiameter", 0.3),
        via_drill=class_value("GetViaDrill", 0.2),
        grid_step=float(grid_step),
        layers=list(pcb_data.board_info.copper_layers),
        board_edge_clearance=max(0.0, edge),
    )

    clearances = {}
    for net_id, net in pcb_data.nets.items():
        if not net_id:
            continue
        value = config.clearance
        try:
            net_class = net_settings.GetEffectiveNetClass(net.name)
            resolved = _mm(pcbnew, net_class.GetClearance())
            if resolved > 0:
                value = resolved
        except Exception:
            pass
        clearances[net_id] = value
    routed_net_ids = sorted(set(net_ids or clearances))
    config.set_net_clearances(clearances, routed_net_ids)
    # Reuse KRT's rule-file resolvers.  PCBData.source_path points at the live
    # board's project, which remains the authority for .kicad_dru rules.
    from kicad_dru import install_layer_clearances, install_track_clearances
    source_path = getattr(pcb_data, "source_path", "") or \
        (board.GetFileName() or "")
    install_layer_clearances(config, None, source_path, pcb_data)
    install_track_clearances(
        config, None, source_path, pcb_data, routed_net_ids=routed_net_ids)
    return config


def _segment_key(segment):
    a = (round(segment.start_x, POSITION_DECIMALS),
         round(segment.start_y, POSITION_DECIMALS))
    b = (round(segment.end_x, POSITION_DECIMALS),
         round(segment.end_y, POSITION_DECIMALS))
    return (frozenset((a, b)), segment.layer, int(segment.net_id),
            round(float(segment.width), POSITION_DECIMALS))


def _native_segment_key(board, pcbnew, track):
    a = (round(_mm(pcbnew, track.GetStart().x), POSITION_DECIMALS),
         round(_mm(pcbnew, track.GetStart().y), POSITION_DECIMALS))
    b = (round(_mm(pcbnew, track.GetEnd().x), POSITION_DECIMALS),
         round(_mm(pcbnew, track.GetEnd().y), POSITION_DECIMALS))
    return (frozenset((a, b)), board.GetLayerName(track.GetLayer()),
            int(track.GetNetCode()),
            round(_mm(pcbnew, track.GetWidth()), POSITION_DECIMALS))


def _layer_map(pcbnew):
    result = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    for index in range(1, 31):
        value = getattr(pcbnew, f"In{index}_Cu", None)
        if value is not None:
            result[f"In{index}.Cu"] = value
    return result


def _native_via_key(board, pcbnew, via):
    layers = tuple(sorted((board.GetLayerName(via.TopLayer()),
                           board.GetLayerName(via.BottomLayer()))))
    return (round(_mm(pcbnew, via.GetPosition().x), POSITION_DECIMALS),
            round(_mm(pcbnew, via.GetPosition().y), POSITION_DECIMALS),
            int(via.GetNetCode()),
            round(_mm(pcbnew, via.GetWidth()), POSITION_DECIMALS),
            round(_mm(pcbnew, via.GetDrillValue()), POSITION_DECIMALS),
            layers)


def _krt_via_key(via):
    return (round(via.x, POSITION_DECIMALS),
            round(via.y, POSITION_DECIMALS), int(via.net_id),
            round(float(via.size), POSITION_DECIMALS),
            round(float(via.drill), POSITION_DECIMALS),
            tuple(sorted(via.layers)))


def apply_gloss(board, results, outcome):
    """Apply prevalidated KRT objects to the live board and render overlays."""
    import pcbnew
    from kicad_parser import mm_to_iu
    from .gloss_visualization import (add_changes_to_board,
                                      disable_intermediate_layers)

    tracks = defaultdict(list)
    vias = {}
    for item in board.GetTracks():
        if item.Type() == pcbnew.PCB_TRACE_T:
            tracks[_native_segment_key(board, pcbnew, item)].append(item)
        elif item.Type() == pcbnew.PCB_VIA_T:
            vias[_native_via_key(board, pcbnew, item)] = item

    remove = []
    seen_segments = set()
    for segment in outcome.input_strip_segments:
        if id(segment) in seen_segments:
            continue
        seen_segments.add(id(segment))
        bucket = tracks.get(_segment_key(segment), [])
        if not bucket:
            raise RuntimeError("Copper changed before Track Gloss apply")
        remove.append(bucket.pop())

    resolved_moves = {}
    via_state = dict(vias)
    for change in outcome.changes.get("vias", []):
        old, new = change.get("old"), change.get("new")
        if old is None or new is None:
            continue
        key = _krt_via_key(old)
        native = via_state.get(key)
        if native is None:
            raise RuntimeError("Via changed before Track Gloss apply")
        identity = id(native)
        if identity not in resolved_moves:
            resolved_moves[identity] = [native, native.GetPosition(), new]
        else:
            resolved_moves[identity][2] = new
        via_state.pop(key, None)
        via_state[_krt_via_key(new)] = native
    via_moves = list(resolved_moves.values())

    layers = _layer_map(pcbnew)
    additions = [segment for result in results
                 for segment in (result.get("new_segments") or [])]
    created = []
    moved = []
    removed = []
    try:
        for segment in additions:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I(
                mm_to_iu(segment.start_x), mm_to_iu(segment.start_y)))
            track.SetEnd(pcbnew.VECTOR2I(
                mm_to_iu(segment.end_x), mm_to_iu(segment.end_y)))
            track.SetWidth(mm_to_iu(segment.width))
            track.SetLayer(layers[segment.layer])
            track.SetNetCode(segment.net_id)
            board.Add(track)
            created.append(track)
        for native, before, new in via_moves:
            moved.append((native, before))
            position = pcbnew.VECTOR2I(mm_to_iu(new.x), mm_to_iu(new.y))
            native.SetStart(position)
            native.SetEnd(position)
        for track in remove:
            board.RemoveNative(track)
            removed.append(track)
    except Exception:
        for native, before in moved:
            native.SetStart(before)
            native.SetEnd(before)
        for track in created:
            try:
                board.RemoveNative(track)
            except Exception:
                pass
        # Removal is deliberately last; failures before it leave input intact.
        if removed:
            raise RuntimeError("Partial native removal; use KiCad Undo")
        raise

    disable_intermediate_layers(board, pcbnew)
    changes_by_stage = {}
    for result in results:
        changes = result.get("track_gloss_changes") or {}
        for kind in ("segments", "vias"):
            for change in changes.get(kind) or []:
                stage = change.get("stage", "G3")
                changes_by_stage.setdefault(
                    stage, {"segments": [], "vias": []})[kind].append(change)
    for stage, changes in sorted(changes_by_stage.items()):
        add_changes_to_board(board, changes, stage=stage)
    for zone in board.Zones():
        zone.SetNeedRefill(True)
    board.BuildConnectivity()
    board.SetModified()
    return len(remove), len(created), len(via_moves)
