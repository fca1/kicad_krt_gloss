"""IPC safety boundaries, independent of a running editor."""
from types import SimpleNamespace
from pathlib import Path
import pytest

from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from kicad_krt_gloss.ipc_snapshot import normalize_snapshot
from kicad_krt_gloss.ipc_rules import protocol, custom_rules_text, checked_custom_rules
from kicad_krt_gloss.ipc_bridge import IpcBoardBridge


def message(name):
    from google.protobuf.message_factory import GetMessageClass
    return GetMessageClass(protocol().FindMessageTypeByName('kiapi.board.commands.' + name))()


@pytest.mark.parametrize('angle', ['0', '30', '-90', '180'])
def test_nightly_pose_translation_preserves_numbers_and_other_content(angle):
    text = f'(kicad_pcb (footprint "x" (transform (translate 12.3 -4.56) (rotate {angle}) (scale 1 1)) (pad "1" (at 1 2))))'
    assert normalize_snapshot(text) == f'(kicad_pcb (footprint "x" (at 12.3 -4.56 {angle}) (pad "1" (at 1 2))))'


@pytest.mark.parametrize('scale', ['2 1', '-1 1', '1 0.5'])
def test_scaled_footprints_are_refused(scale):
    with pytest.raises(RuntimeError, match='scaled'):
        normalize_snapshot(f'(kicad_pcb (footprint "x" (transform (translate 1 2) (rotate 30) (scale {scale}))))')


def test_multiple_poses_preserve_interleaved_legacy_footprints_and_quoted_parentheses():
    pose_a = '(transform (translate 12.30 -4.56) (rotate 3e1) (scale 1 1))'
    pose_b = '(transform (translate -5 6) (rotate -90) (scale 1.0 1e0))'
    text = (f'(kicad_pcb (footprint "a" {pose_a} (property "Value" "part (A)"))\n'
            '(segment (start 1 2) (end 3 4))\n'
            '(footprint "legacy" (at 7 8 10) (pad "1" (at 0 0)))\n'
            f'(footprint "b" {pose_b} (pad "2" (at 1 2)))\n(end))')
    expected = text.replace(pose_a, '(at 12.30 -4.56 3e1)').replace(pose_b, '(at -5 6 -90)')
    assert normalize_snapshot(text) == expected


@pytest.mark.parametrize('pose', [
    '(transform (translate 1 2) (rotate 30) (scale 1 1)) '
    '(transform (translate 3 4) (rotate 60) (scale 1 1))',
    '(transform (translate 1 2) (rotate 30))',
    '(transform (translate 1e999 2) (rotate 30) (scale 1 1))',
])
def test_malformed_pose_after_valid_footprint_still_refused(pose):
    text = ('(kicad_pcb (footprint "valid" '
            '(transform (translate 1 2) (rotate 30) (scale 1 1))) '
            f'(footprint "invalid" {pose}))')
    with pytest.raises(RuntimeError, match='not supported|unsupported'):
        normalize_snapshot(text)


@pytest.fixture
def import_cycle(monkeypatch):
    """Count real adapter imports while supplying an editor-free snapshot."""
    from dgloss import krt_api
    calls = {'states': 0, 'parsed': [], 'tracks': 0, 'vias': 0}
    live = ['original board', '{}', '(version 1)']

    def items(kind):
        calls[kind] += 1
        return []

    board = SimpleNamespace(get_tracks=lambda: items('tracks'), get_vias=lambda: items('vias'))
    bridge = IpcBoardBridge(SimpleNamespace(get_board=lambda: board))

    def state():
        calls['states'] += 1
        return tuple(live)

    def parse(path):
        text = Path(path).read_text(encoding='utf-8')
        calls['parsed'].append(text)
        return SimpleNamespace(nets={len(calls['parsed']): SimpleNamespace(name=text)}, segments=[])

    monkeypatch.setattr(krt_api, 'parse_kicad_pcb', parse)
    monkeypatch.setattr(bridge, '_state', state)
    monkeypatch.setattr(bridge, 'selected_net_names', lambda _: {live[0]})
    try:
        yield bridge, board, live, calls
    finally:
        bridge.close()


def test_initial_cycle_shares_one_import_then_each_dialog_action_is_fresh(import_cycle):
    bridge, board, live, calls = import_cycle
    with bridge.initial_import():
        assert bridge.selected_net_ids(board) == [1]
        first = bridge.build_pcb_data(board)
        assert bridge.build_pcb_data(board) is first
        assert calls == {'states': 2, 'parsed': ['original board'], 'tracks': 1, 'vias': 1}
    assert bridge._initial_data is None and not bridge._initial_import_active
    live[:] = ['changed board', '{"rules": "changed"}', '(version 1) ; changed']
    second = bridge.build_pcb_data(board)
    third = bridge.build_pcb_data(board)
    assert second is not first and third is not second
    assert bridge.state == tuple(live)
    assert calls['states'] == 6
    assert calls['parsed'] == ['original board', 'changed board', 'changed board']


def test_second_initial_cycle_reloads_net_ids_and_never_reuses_mutated_data(import_cycle):
    bridge, board, live, calls = import_cycle
    with bridge.initial_import():
        assert bridge.selected_net_ids(board) == [1]
        first = bridge.data
        first.segments.append('engine mutation')
    live[0] = 'new net name'
    with bridge.initial_import():
        assert bridge.selected_net_ids(board) == [2]
        assert bridge.data is not first
        assert bridge.data.segments == []
        assert bridge.net_ids == {'new net name': 2}
    assert bridge._initial_data is None and not bridge._initial_import_active
    assert calls['states'] == 4


def test_initial_cycle_exception_clears_reuse(import_cycle):
    bridge, board, _live, calls = import_cycle
    with pytest.raises(ValueError, match='cancel opening'):
        with bridge.initial_import():
            first = bridge.build_pcb_data(board)
            raise ValueError('cancel opening')
    assert bridge._initial_data is None and not bridge._initial_import_active
    assert bridge.build_pcb_data(board) is not first
    assert calls['states'] == 4


def test_initial_cycle_keeps_torn_import_guard(import_cycle, monkeypatch):
    bridge, board, live, _calls = import_cycle
    states = iter([tuple(live), ('modified during import', live[1], live[2])])
    monkeypatch.setattr(bridge, '_state', lambda: next(states))
    with pytest.raises(RuntimeError, match='during IPC import'):
        with bridge.initial_import():
            bridge.build_pcb_data(board)
    assert bridge._initial_data is None and not bridge._initial_import_active


@pytest.mark.parametrize('changed_field', [0, 1, 2])
def test_reused_opening_snapshot_still_rejects_changed_board_rules_or_dru(import_cycle, changed_field):
    bridge, board, live, _calls = import_cycle
    with bridge.initial_import():
        first = bridge.build_pcb_data(board)
        live[changed_field] += ' changed'
        assert bridge.build_pcb_data(board) is first
        outcome = SimpleNamespace(stats={'g5_valid': True}, input_strip_segments=[], changes={})
        with pytest.raises(RuntimeError, match='changed during Gloss'):
            bridge.apply_outcome(board, [], outcome)


@pytest.mark.parametrize('mode', ['dialog', 'direct', 'no-op', 'failure'])
def test_entry_releases_initial_snapshot_before_event_loop_or_exit(import_cycle, monkeypatch, mode):
    import importlib.util
    import sys
    import types
    import kipy
    bridge, board, live, calls = import_cycle
    path = Path(__file__).resolve().parents[1] / 'kicad_krt_gloss/ipc_entry.py'
    spec = importlib.util.spec_from_file_location('_entry_scope_test', path)
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    errors, event_loops = [], []

    class Plugin:
        _settings_dialog = object() if mode == 'dialog' else None

        def Run(self):
            assert bridge.selected_net_ids(board) == [1]
            first = bridge.build_pcb_data(board)
            if mode == 'dialog':
                assert bridge.build_pcb_data(board) is first  # Initial EB capture.
            assert len(calls['parsed']) == 1
            if mode == 'no-op':
                outcome = SimpleNamespace(stats={'g5_valid': True}, input_strip_segments=[], changes={})
                assert bridge.apply_outcome(board, [], outcome) == (0, 0, 0, None)
            if mode == 'failure':
                raise ValueError('opening failed')

    def main_loop():
        assert bridge._initial_data is None and not bridge._initial_import_active
        event_loops.append(True)
        live[0] = 'changed after dialog opened'
        bridge.build_pcb_data(board)
        assert calls['parsed'] == ['original board', live[0]]

    modules = {
        '_krg_ipc.runtime': SimpleNamespace(configure_krt_runtime=lambda: None),
        '_krg_ipc.ipc_bridge': SimpleNamespace(IpcBoardBridge=lambda _: bridge),
        '_krg_ipc.action_plugin': SimpleNamespace(KiCadKrtGlossPlugin=Plugin),
        '_krg_ipc.branch_selection_prototype': SimpleNamespace(activate=lambda _: None),
    }
    entry.importlib = SimpleNamespace(import_module=modules.__getitem__)
    monkeypatch.setitem(sys.modules, 'wx', SimpleNamespace(
        App=lambda _: SimpleNamespace(MainLoop=main_loop),
        MessageBox=lambda *args: errors.append(args), OK=1, ICON_ERROR=2))
    monkeypatch.setitem(sys.modules, '_krg_ipc', types.ModuleType('_krg_ipc'))
    monkeypatch.setattr(kipy, 'KiCad', lambda **_: object())
    monkeypatch.setenv('KICAD_API_SOCKET', 'test-explicit-socket')
    monkeypatch.setenv('KRG_IPC', '1')
    assert entry.main() == (1 if mode == 'failure' else 0)
    assert bridge._initial_data is None and not bridge._initial_import_active
    assert len(event_loops) == (1 if mode == 'dialog' else 0)
    assert bool(errors) == (mode == 'failure')


def test_live_rule_units_and_condition_are_preserved():
    response = message('CustomRulesResponse')
    response.status = 2
    rule = response.rules.add(name='clearance', condition="A.NetName == 'power'")
    rule.layer_mode = 1
    constraint = rule.constraints.add(type=1)
    constraint.numeric.min = 250000
    from dgloss.krt_api import parse_dru
    rules, notes = parse_dru(custom_rules_text(response))
    assert not notes
    assert rules[0].constraints == {'clearance': {'min': .25}}
    assert rules[0].layer_clause == 'outer'
    assert rules[0].condition_src == rule.condition


def test_unknown_constraint_options_fail_closed():
    response = message('CustomRulesResponse'); response.status = 2
    rule = response.rules.add(name='with option')
    rule.constraints.add(type=1).options.append(1)
    with pytest.raises(RuntimeError, match='options'):
        custom_rules_text(response)


def test_saved_layer_mask_retained_and_stale_rule_rejected(tmp_path):
    response = message('CustomRulesResponse'); response.status = 2
    rule = response.rules.add(name='silk')
    rule.constraints.add(type=9).numeric.min = 800000
    board = SimpleNamespace(document=SimpleNamespace(project=SimpleNamespace(path=str(tmp_path)),
                                                     board_filename='board.kicad_pcb'))
    text = '(version 1) (rule "silk" (layer "?.Silkscreen") (constraint text_height (min .8)))'
    path = tmp_path / 'board.kicad_dru'; path.write_text(text)
    assert checked_custom_rules(board, response) == text
    path.write_text(text.replace('.8', '.9'))
    with pytest.raises(RuntimeError, match='differs'):
        checked_custom_rules(board, response)


def test_stale_board_rejected_before_any_mutation():
    bridge = object.__new__(IpcBoardBridge)
    bridge.state = ('before', '', '')
    bridge._state = lambda: ('after', '', '')
    with pytest.raises(RuntimeError, match='changed during Gloss'):
        bridge.apply_outcome(object(), [], SimpleNamespace(stats={'g5_valid': True}))


def test_ipc_entry_never_uses_default_socket():
    text = (Path(__file__).resolve().parents[1] / 'kicad_krt_gloss/ipc_entry.py').read_text()
    assert "os.environ.get('KICAD_API_SOCKET')" in text


def test_partial_delete_rolls_back_transaction():
    from kipy.board_types import Track
    from kipy.proto.common.types.base_types_pb2 import DocumentSpecifier
    bridge = object.__new__(IpcBoardBridge)
    bridge.state = ('board', '', '')
    bridge._state = lambda: bridge.state
    segment = object()
    track = Track(); track.proto.id.value = 'track-one'
    bridge.import_index = {'track-one': segment}
    bridge.tracks, bridge.vias = [track], []
    calls = []
    board = SimpleNamespace(
        begin_commit=lambda: 'transaction',
        drop_commit=lambda commit: calls.append(('drop', commit)),
        push_commit=lambda *a: calls.append(('push', a)),
        document=DocumentSpecifier(),
        client=SimpleNamespace(send=lambda *a: SimpleNamespace(status=1, deleted_items=[])))
    outcome = SimpleNamespace(stats={'g5_valid': True}, input_strip_segments=[segment], changes={})
    with pytest.raises(RuntimeError, match='part of the track deletion'):
        bridge.apply_outcome(board, [], outcome)
    assert calls == [('drop', 'transaction')]


def test_no_op_does_not_start_transaction():
    bridge = object.__new__(IpcBoardBridge)
    bridge.state = ('board', '', '')
    bridge._state = lambda: bridge.state
    bridge.import_index, bridge.tracks, bridge.vias = {}, [], []
    outcome = SimpleNamespace(stats={'g5_valid': True}, input_strip_segments=[], changes={})
    assert bridge.apply_outcome(object(), [], outcome) == (0, 0, 0, None)


def test_manifest_matches_installed_kicad_schema():
    import json, jsonschema
    root = Path(__file__).resolve().parents[1]
    schema_path = Path('D:/kicad/10.99/share/kicad/schemas/api.v1.schema.json')
    if not schema_path.exists():
        pytest.skip('Local KiCad schema unavailable')
    jsonschema.validate(json.loads((root/'kicad_krt_gloss/plugin.json').read_text()),
                        json.loads(schema_path.read_text()))
