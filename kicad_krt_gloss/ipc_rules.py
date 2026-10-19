"""Read live KiCad rules, then let the unmodified KRT parser interpret them.

The private descriptor pool extends kicad-python 0.8 with KiCad 11 rule reads.
ipc_protocol.pb is generated from KiCad dcadf9baa30d43d7d1b3d0342345f05ec0da26e1
api/proto (GPL-3.0-or-later), not from KRT. No global protobuf registrations.
"""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache()
def protocol():
    from google.protobuf.descriptor_pb2 import FileDescriptorSet
    from google.protobuf.descriptor_pool import DescriptorPool
    data = FileDescriptorSet.FromString(Path(__file__).with_name('ipc_protocol.pb').read_bytes())
    pool = DescriptorPool()
    for file in data.file:
        pool.Add(file)
    return pool


def read_rules(board, custom=False):
    from google.protobuf.message_factory import GetMessageClass
    request, response = (('GetCustomDesignRules', 'CustomRulesResponse') if custom
                         else ('GetBoardDesignRules', 'BoardDesignRulesResponse'))
    def cls(name):
        return GetMessageClass(protocol().FindMessageTypeByName('kiapi.board.commands.' + name))
    command = cls(request)()
    command.board.ParseFromString(board.document.SerializeToString())
    return board.client.send(command, cls(response))


def enum_name(message, field, value):
    return message.DESCRIPTOR.fields_by_name[field].enum_type.values_by_number[value].name


def custom_rules_text(response):
    """Lossless for supported clauses; refuse unknown syntax rather than drop it."""
    if response.status not in (1, 2):  # CRS_NONE / CRS_VALID
        raise RuntimeError('KiCad custom design rules are invalid: ' + response.error_text)
    output = ['(version 1)']
    aliases = {'max_uncoupled': 'diff_pair_uncoupled', 'net_chain_stub_length': 'stub_length',
               'net_chain_return_path': 'return_path'}
    unitless = {'via_count', 'min_resolved_spokes', 'track_angle', 'solder_paste_rel_margin',
                'microvia_stack_depth', 'microvia_aspect_ratio'}
    for rule in response.rules:
        parts = ['(rule ' + json.dumps(rule.name)]
        if rule.condition:
            parts.append('(condition ' + json.dumps(rule.condition) + ')')
        layer_kind = rule.WhichOneof('layer_condition')
        if layer_kind == 'single_layer':
            from kipy.util.board_layer import canonical_name
            parts.append('(layer ' + json.dumps(canonical_name(rule.single_layer)) + ')')
        elif layer_kind == 'layer_mode':
            parts.append('(layer ' + {1: 'outer', 2: 'inner'}[rule.layer_mode] + ')')
        if rule.severity not in (0, 8):
            parts.append('(severity ' + enum_name(rule, 'severity', rule.severity)[3:].lower() + ')')
        for constraint in rule.constraints:
            token = enum_name(constraint, 'type', constraint.type)[5:].lower()
            token = aliases.get(token, token)
            if constraint.options or constraint.HasField('name'):
                raise RuntimeError(f'IPC rule {rule.name}: named/options constraints are not supported')
            kind = constraint.WhichOneof('value')
            if kind == 'numeric':
                values = []
                for key in ('min', 'opt', 'max'):
                    if constraint.numeric.HasField(key):
                        number = getattr(constraint.numeric, key)
                        value = str(number) if token in unitless else f'{number / 1e6:.9f}mm'
                        values.append(f'({key} {value})')
                body = ' '.join(values)
            elif kind == 'disallow':
                body = ' '.join(enum_name(constraint.disallow, 'types', v)[5:].lower()
                                for v in constraint.disallow.types)
            elif kind == 'assertion_expression':
                body = json.dumps(constraint.assertion_expression)
            elif kind == 'zone_connection':
                body = {2: 'none', 3: 'thermal_reliefs', 4: 'solid'}[constraint.zone_connection]
            else:
                raise RuntimeError(f'IPC rule {rule.name}: unsupported constraint {token}')
            parts.append(f'(constraint {token} {body})')
        output.append(' '.join(parts) + ')')
    return '\n'.join(output) + '\n'


def checked_custom_rules(board, response):
    """KiCad's rule IPC omits arbitrary layer masks: preserve the source text.

As with the native KRT adapter, the sibling DRU is authoritative for custom
rule syntax. Compare all IPC-representable semantics; refuse stale files.
"""
    from dgloss.krt_api import parse_dru
    live_text = custom_rules_text(response)
    source = (Path(board.document.project.path) /
              Path(board.document.board_filename).with_suffix('.kicad_dru'))
    if not source.exists():
        if response.rules:
            raise RuntimeError('Custom rules require the matching saved .kicad_dru file')
        return live_text
    disk_text = source.read_text(encoding='utf-8-sig')
    live, _ = parse_dru(live_text)
    disk, notes = parse_dru(disk_text)
    if notes or len(live) != len(disk):
        raise RuntimeError('Saved custom rules do not match the live IPC rules')
    for a, b in zip(live, disk):
        if ((a.name, a.condition_src, a.constraints, a.severity) !=
                (b.name, b.condition_src, b.constraints, b.severity) or
                (a.layer_clause is not None and a.layer_clause != b.layer_clause)):
            raise RuntimeError(f'Custom rule {a.name!r} differs from its saved .kicad_dru; save rules and retry')
    return disk_text


MINIMUMS = {
    'min_clearance': 'min_clearance', 'min_connection_width': 'min_connection',
    'min_track_width': 'min_track_width', 'min_via_annular_width': 'min_via_annular_width',
    'min_via_size': 'min_via_diameter', 'min_through_drill': 'min_through_hole_diameter',
    'min_microvia_size': 'min_microvia_diameter', 'min_microvia_drill': 'min_microvia_drill',
    'copper_edge_clearance': 'min_copper_edge_clearance',
    'hole_clearance': 'min_hole_clearance', 'hole_to_hole_min': 'min_hole_to_hole',
}


def project_settings(board):
    response = read_rules(board)
    custom = read_rules(board, custom=True)
    constraints = response.rules.constraints
    rules = {key: getattr(constraints, field).value_nm / 1e6
             for field, key in MINIMUMS.items() if constraints.HasField(field)}
    classes = []
    for cls in board.get_project().get_net_classes():
        row = {'name': cls.name, 'priority': cls.priority}
        for key in ('clearance', 'track_width', 'via_diameter', 'via_drill',
                    'diff_pair_gap', 'diff_pair_via_gap', 'microvia_diameter', 'microvia_drill'):
            value = getattr(cls, key)
            if value is not None:
                row[key] = value / 1e6
        if cls.diff_pair_track_width is not None:
            row['diff_pair_width'] = cls.diff_pair_track_width / 1e6
        classes.append(row)
    effective = board.get_netclass_for_nets(board.get_nets())
    assignments = {name: cls.constituents or [cls.name] for name, cls in effective.items()}
    project = {'board': {'design_settings': {'rules': rules}},
               'net_settings': {'classes': classes, 'netclass_assignments': assignments}}
    return project, checked_custom_rules(board, custom)
