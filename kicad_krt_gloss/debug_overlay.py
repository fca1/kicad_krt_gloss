"""Shared, PCB-independent Track Gloss debug-overlay policy and geometry."""

from __future__ import annotations

import math
import os
import re
import tempfile


LAYER_NAME = "TrackGloss Changes"
USER_LAYER_NAMES = tuple(f"User.{index}" for index in range(1, 10))


def line_parts(start, end, dash=0.30, gap=0.20):
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


def overlay_lines(changes):
    """Yield ``(start, end, width)`` for the final before/after overlay."""
    for change in changes.get("segments") or []:
        new = change.get("new")
        if new is not None:
            yield ((new.start_x, new.start_y), (new.end_x, new.end_y),
                   max(0.03, new.width))
    for change in changes.get("segments") or []:
        old = change.get("old")
        if old is None:
            continue
        for start, end in line_parts(
                (old.start_x, old.start_y), (old.end_x, old.end_y)):
            yield start, end, max(0.03, min(old.width, 0.10))

    for change in changes.get("vias") or []:
        old, new = change["old"], change["new"]
        radius = max(getattr(new, "size", 0.3) / 2.0, 0.15)
        for via, dashed in ((new, False), (old, True)):
            points = [
                (via.x + radius * math.cos(2 * math.pi * i / 20),
                 via.y + radius * math.sin(2 * math.pi * i / 20))
                for i in range(21)
            ]
            for index in range(20):
                if not dashed or index % 2 == 0:
                    yield points[index], points[index + 1], 0.05
        yield (old.x, old.y), (new.x, new.y), 0.05


def door_lines(changes):
    """Yield the applied G3.6 doors that need a dash-dot marker."""
    for door in changes.get("doors") or []:
        if isinstance(door, dict):
            start, end = door.get("edge_a"), door.get("edge_b")
        else:
            start = getattr(door, "edge_a", None)
            end = getattr(door, "edge_b", None)
        if start is not None and end is not None and start != end:
            yield tuple(start), tuple(end), 0.12


def choose_user_layer(layer_names, occupied, requested="auto"):
    """Choose an owned layer first, otherwise the lowest genuinely free one."""
    if requested != "auto":
        if requested not in USER_LAYER_NAMES:
            raise ValueError(f"unsupported debug layer: {requested}")
        display_name = layer_names.get(requested, requested)
        if (display_name == LAYER_NAME or
                requested not in occupied and display_name in (requested, "")):
            return requested
        raise ValueError(f"{requested} is already in use")

    owned = [name for name in USER_LAYER_NAMES
             if layer_names.get(name) == LAYER_NAME]
    if owned:
        return owned[0]

    for name in USER_LAYER_NAMES:
        display_name = layer_names.get(name, name)
        if name not in occupied and display_name in (name, ""):
            return name
    return None


def _matching_paren(text, start):
    """Use KRT's S-expression boundary helper."""
    from kicad_parser import find_matching_paren
    return find_matching_paren(text, start)


def _layer_table(content):
    match = re.search(r"(?m)^\s*\(layers\s*$", content)
    if match is None:
        raise ValueError("PCB has no layers table")
    end = _matching_paren(content, match.start())
    return match.start(), end + 1, content[match.start():end + 1]


def _file_layer_inventory(content):
    start, end, table = _layer_table(content)
    entries = {}
    pattern = re.compile(
        r'\(\s*\d+\s+"(User\.(?:[1-9]))"\s+user(?:\s+"([^"]*)")?\s*\)')
    for match in pattern.finditer(table):
        canonical, display = match.groups()
        entries[canonical] = display or canonical

    body = content[:start] + content[end:]
    occupied = set(re.findall(
        r'\((?:layer|layers)\s+(?:"[^"]*"\s+)*"(User\.[1-9])"', body))
    return entries, occupied


def _set_file_layer_name(content, layer_name, display_name=None):
    start, end, table = _layer_table(content)
    entry = re.compile(
        rf'(\(\s*\d+\s+"{re.escape(layer_name)}"\s+user)'
        rf'(?:\s+"[^"]*")?(\s*\))')
    suffix = f' "{display_name}"' if display_name else ""
    if entry.search(table):
        table = entry.sub(rf'\1{suffix}\2', table, count=1)
    else:
        index = int(layer_name.split(".", 1)[1])
        layer_id = 37 + 2 * index
        close = table.rfind(")")
        table = (table[:close] +
                 f'\n\t\t({layer_id} "{layer_name}" user{suffix})' +
                 table[close:])
    return content[:start] + table + content[end:]


def _name_file_layer(content, layer_name):
    return _set_file_layer_name(content, layer_name, LAYER_NAME)


def _remove_layer_gr_lines(content, layer_name):
    starts = [match.start() for match in re.finditer(r"\(gr_line\b", content)]
    for start in reversed(starts):
        end = _matching_paren(content, start) + 1
        if re.search(rf'\(layer\s+"{re.escape(layer_name)}"\)',
                     content[start:end]):
            content = content[:start] + content[end:]
    return content


def _write_atomic(path, content):
    directory = os.path.dirname(os.path.abspath(path))
    handle, temporary = tempfile.mkstemp(
        prefix=".track_gloss_", suffix=".kicad_pcb", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as output:
            output.write(content)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_cli_debug_overlay(path, changes, requested="auto"):
    """Add the final Track Gloss overlay to a CLI-written KiCad PCB."""
    with open(path, encoding="utf-8") as source:
        content = source.read()
    layer_names, occupied = _file_layer_inventory(content)
    owned = [name for name in USER_LAYER_NAMES
             if layer_names.get(name) == LAYER_NAME]
    has_changes = bool(changes.get("segments") or changes.get("vias") or
                       changes.get("doors"))
    if not has_changes:
        if not owned:
            return None
        for name in owned:
            content = _remove_layer_gr_lines(content, name)
        for name in owned[1:]:
            content = _set_file_layer_name(content, name)
        _write_atomic(path, content)
        return owned[0]

    layer_name = choose_user_layer(layer_names, occupied, requested)
    if layer_name is None:
        return None

    for name in set(owned) | {layer_name}:
        content = _remove_layer_gr_lines(content, name)
    for name in owned:
        if name != layer_name:
            content = _set_file_layer_name(content, name)
    content = _name_file_layer(content, layer_name)
    from kicad_writer import generate_gr_line_sexpr
    graphics = [generate_gr_line_sexpr(start, end, width, layer_name)
                for start, end, width in overlay_lines(changes)]
    # KiCad calls the requested "trait mixte" dash-dot. KRT's writer emits
    # solid lines, so retain its S-expression format and change only the style.
    graphics.extend(
        generate_gr_line_sexpr(start, end, width, layer_name).replace(
            "(type solid)", "(type dash_dot)")
        for start, end, width in door_lines(changes))
    graphics = "\n".join(graphics)
    final_paren = content.rfind(")")
    content = content[:final_paren] + "\n" + graphics + "\n" + content[final_paren:]

    _write_atomic(path, content)
    return layer_name
