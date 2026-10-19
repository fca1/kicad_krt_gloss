"""Optional before/after drawing, owned by a named group on a free User layer."""
from .debug_overlay import overlay_lines

GROUP_NAME = 'KRT Gloss changes (IPC)'


def add_overlay(board, changes):
    from kipy.board_types import BoardShape, Group
    from kipy.geometry import Vector2
    from kipy.util.board_layer import canonical_name
    from dgloss.krt_api import mm_to_iu
    groups = [g for g in board.get_groups() if g.name == GROUP_NAME]
    if len(groups) > 1:
        raise RuntimeError('Ambiguous Gloss overlay groups')
    owned = {uid.value for g in groups for uid in g.proto.items}
    shapes = board.get_shapes()
    old = [s for s in shapes if s.id.value in owned]
    if len(old) != len(owned):
        raise RuntimeError('Gloss overlay group contains non-graphic objects')
    occupied = {s.layer for s in shapes if s.id.value not in owned}
    occupied.update(t.layer for t in board.get_text())
    candidates = [layer for layer in board.get_enabled_layers()
                  if canonical_name(layer).startswith('User.') and
                  canonical_name(layer)[5:].isdigit() and layer not in occupied]
    if not candidates:
        return None
    layer = sorted(candidates, key=lambda l: int(canonical_name(l)[5:]))[0]
    new = []
    for start, end, width in overlay_lines(changes):
        shape = BoardShape()
        shape.layer = layer
        shape.proto.shape.segment.start.CopyFrom(Vector2.from_xy_mm(*start).proto)
        shape.proto.shape.segment.end.CopyFrom(Vector2.from_xy_mm(*end).proto)
        shape.proto.shape.attributes.stroke.width.value_nm = mm_to_iu(max(.03, width))
        new.append(shape)
    if old:
        board.remove_items(old)
    if groups:
        board.remove_items(groups)
    if new:
        created = board.create_items(new)
        if len(created) != len(new):
            raise RuntimeError('Incomplete IPC overlay')
        group = Group()
        group.proto.name = GROUP_NAME
        group.items = created
        if len(board.create_items(group)) != 1:
            raise RuntimeError('IPC overlay group creation failed')
    return canonical_name(layer) if new else None
