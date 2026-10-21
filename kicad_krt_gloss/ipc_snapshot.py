"""Translate KiCad 11 unit-scale footprint poses for the KRT 0.23 parser."""
import math
import re

NUMBER = r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)'
POSE = re.compile(r'\(transform\s*\(translate\s+' + NUMBER + r'\s+' + NUMBER +
                  r'\)\s*\(rotate\s+' + NUMBER + r'\)\s*\(scale\s+' + NUMBER +
                  r'\s+' + NUMBER + r'\)\s*\)')


def normalize_snapshot(text):
    from dgloss.krt_api import iter_footprint_blocks
    parts, offset = [], 0
    for start, end, block, reference, _ in iter_footprint_blocks(text):
        if '(transform' not in block:
            continue
        matches = list(POSE.finditer(block))
        if len(matches) != 1 or block.count('(transform') != 1:
            raise RuntimeError(f'{reference}: unsupported KiCad footprint transform')
        match = matches[0]
        x, y, angle, sx, sy = map(float, match.groups())
        if not all(map(math.isfinite, (x, y, angle, sx, sy))) or (sx, sy) != (1., 1.):
            raise RuntimeError(f'{reference}: scaled footprints are not supported by KRT 0.23.1')
        pose = '(at ' + ' '.join(match.groups()[:3]) + ')'
        parts.extend((text[offset:start], block[:match.start()], pose, block[match.end():]))
        offset = end
    if not parts:
        return text
    parts.append(text[offset:])
    return ''.join(parts)
