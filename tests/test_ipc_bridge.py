"""Via updates retain native identity and properties through an IPC transaction."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kipy.board_types import Net, Via
from kipy.geometry import Vector2
from kipy.proto.board.board_types_pb2 import PadStackType

from kicad_krt_gloss.ipc_bridge import IpcBoardBridge
from kicad_krt_gloss import ipc_overlay


VIA_ID = '3c688bc1-8576-4519-853d-143059e2d78a'


def native_via():
    via = Via()
    via.proto.id.value = VIA_ID
    via.proto.parent.value = '1784e357-bb2e-487d-95be-694d5373a009'
    via.position = Vector2.from_xy(1000000, 2000000)
    via.net = Net(name='/B')
    via.proto.net.code.value = 97  # Native codes need not equal the KRT code.
    via.locked = True
    via.padstack.type = PadStackType.PST_FRONT_INNER_BACK
    for i, layer in enumerate(via.padstack.copper_layers):
        diameter = 600000 + i * 20000
        layer.size = Vector2.from_xy(diameter, diameter)
    via.drill_diameter = 300000
    return via


def move(old, new):
    def geometry(point):
        return SimpleNamespace(x=point[0], y=point[1], size=.6, drill=.3, net_id=1)
    return {'old': geometry(old), 'new': geometry(new)}


def setup_transaction(monkeypatch, moves):
    original = native_via()
    bridge = object.__new__(IpcBoardBridge)
    bridge.state = ('board', '{}', '(version 1)')
    bridge._state = Mock(return_value=bridge.state)
    bridge.import_index, bridge.tracks, bridge.vias = {}, [], [original]
    bridge.data = SimpleNamespace(nets={1: SimpleNamespace(name='/B')})
    overlay = Mock(return_value=None)
    monkeypatch.setattr(ipc_overlay, 'add_overlay', overlay)
    board = SimpleNamespace(
        begin_commit=Mock(return_value='via-transaction'),
        update_items=Mock(side_effect=lambda items: [Via(proto=item.proto) for item in items]),
        create_items=Mock(side_effect=AssertionError('No track creation expected')),
        push_commit=Mock(), drop_commit=Mock(), get_zones=Mock(return_value=[]))
    outcome = SimpleNamespace(stats={'g5_valid': True}, input_strip_segments=[],
                              changes={'vias': moves}, visual_changes={})
    return bridge, board, outcome, original, overlay


def without_position(via):
    proto = type(via.proto)()
    proto.CopyFrom(via.proto)
    proto.ClearField('position')
    return proto.SerializeToString()


def test_via_update_preserves_uuid_and_every_property_except_position(monkeypatch):
    bridge, board, outcome, original, overlay = setup_transaction(
        monkeypatch, [move((1., 2.), (3.125001, -4.250002))])
    original_bytes = original.proto.SerializeToString()

    assert bridge.apply_outcome(board, [], outcome) == (0, 0, 1, None)

    board.update_items.assert_called_once()
    updates = board.update_items.call_args.args[0]
    assert len(updates) == 1
    updated = updates[0]
    assert updated is not original
    assert updated.id.value == VIA_ID
    assert (updated.position.x, updated.position.y) == (3125001, -4250002)
    assert without_position(updated) == without_position(original)
    assert original.proto.SerializeToString() == original_bytes
    board.push_commit.assert_called_once_with('via-transaction', 'KRT Gloss')
    board.drop_commit.assert_not_called()
    board.create_items.assert_not_called()
    overlay.assert_called_once_with(board, outcome.visual_changes)


def test_multiple_steps_of_one_via_publish_one_update_with_original_uuid(monkeypatch):
    points = [(1., 2.), (2.5, 3.75), (-1.25, 6.), (7.000001, -8.000002)]
    bridge, board, outcome, original, _overlay = setup_transaction(
        monkeypatch, [move(a, b) for a, b in zip(points, points[1:])])
    original_bytes = original.proto.SerializeToString()

    assert bridge.apply_outcome(board, [], outcome) == (0, 0, 1, None)

    board.update_items.assert_called_once()
    updates = board.update_items.call_args.args[0]
    assert len(updates) == 1
    assert updates[0].id.value == VIA_ID
    assert (updates[0].position.x, updates[0].position.y) == (7000001, -8000002)
    assert without_position(updates[0]) == without_position(original)
    assert original.proto.SerializeToString() == original_bytes
    board.push_commit.assert_called_once_with('via-transaction', 'KRT Gloss')
    board.drop_commit.assert_not_called()


@pytest.mark.parametrize('returned_id', ['', 'ed5950ec-b11f-41d5-aa2e-887b38949e74'])
def test_wrong_returned_via_uuid_drops_transaction_without_publication(monkeypatch, returned_id):
    bridge, board, outcome, original, overlay = setup_transaction(
        monkeypatch, [move((1., 2.), (4., 5.))])
    original_bytes = original.proto.SerializeToString()

    def mismatched_receipt(items):
        reply = Via(proto=items[0].proto)
        reply.proto.id.value = returned_id
        return [reply]

    board.update_items.side_effect = mismatched_receipt
    with pytest.raises(RuntimeError, match='did not move the certified vias exactly'):
        bridge.apply_outcome(board, [], outcome)
    assert board.update_items.call_args.args[0][0].id.value == VIA_ID
    board.drop_commit.assert_called_once_with('via-transaction')
    board.push_commit.assert_not_called()
    board.get_zones.assert_not_called()
    overlay.assert_not_called()
    assert original.proto.SerializeToString() == original_bytes


def test_correct_uuid_with_wrong_position_still_drops_transaction(monkeypatch):
    bridge, board, outcome, original, overlay = setup_transaction(
        monkeypatch, [move((1., 2.), (4., 5.))])
    board.update_items.side_effect = lambda items: [Via(proto=original.proto)]
    with pytest.raises(RuntimeError, match='did not move the certified vias exactly'):
        bridge.apply_outcome(board, [], outcome)
    board.drop_commit.assert_called_once_with('via-transaction')
    board.push_commit.assert_not_called()
    overlay.assert_not_called()
