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
