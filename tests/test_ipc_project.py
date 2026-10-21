"""Project-scoped KiCad 11 net classes with the isolated kicad-python 0.8 pool."""
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.protobuf import descriptor_pool
from google.protobuf.message_factory import GetMessageClass
from kipy.errors import ApiError
from kipy.project_types import NetClass
from kipy.proto.common.commands import project_commands_pb2
from kipy.proto.common.types.base_types_pb2 import DocumentSpecifier
from kipy.proto.common.types import project_settings_pb2

from kicad_krt_gloss import ipc_rules


def make_board(path, name='PCB project avec espaces', response=None):
    document = DocumentSpecifier(board_filename='independent board name.kicad_pcb')
    document.project.name = name
    document.project.path = path
    send = Mock(return_value=(response if response is not None
                              else project_commands_pb2.NetClassesResponse()))
    board = SimpleNamespace(document=document, client=SimpleNamespace(send=send),
                            get_project=Mock(side_effect=AssertionError(
                                'The SDK 0.8 project-wide empty request must not be used')))
    return board, send


def class_response():
    response = project_commands_pb2.NetClassesResponse()
    default = response.net_classes.add(name='Default', priority=2147483647,
                                      type=project_settings_pb2.NCT_EXPLICIT)
    settings = default.board
    for field, value in {
            'clearance': 225000, 'track_width': 310000,
            'diff_pair_track_width': 170000, 'diff_pair_gap': 180000,
            'diff_pair_via_gap': 0}.items():
        getattr(settings, field).value_nm = value
    settings.via_stack.copper_layers.add().size.x_nm = 650000
    settings.via_stack.drill.diameter.x_nm = 325000
    settings.microvia_stack.copper_layers.add().size.x_nm = 275000
    settings.microvia_stack.drill.diameter.x_nm = 125000
    response.net_classes.add(name='Power class', priority=7,
                             type=project_settings_pb2.NCT_EXPLICIT)
    return response


@pytest.mark.parametrize('spelling', ['plain', 'trailing', 'duplicate-trailing',
                                     'dot-components', 'forward-slashes'])
def test_request_targets_exact_project_and_keeps_document_unchanged(tmp_path, spelling):
    path = str(tmp_path / 'Projet avec espaces é')
    if spelling == 'trailing':
        path += os.sep
    elif spelling == 'duplicate-trailing':
        path += os.sep * 3
    elif spelling == 'dot-components':
        path = os.path.join(path, 'temporary', '..')
    elif spelling == 'forward-slashes':
        path = path.replace(os.sep, '/')
    board, send = make_board(path)
    before = board.document.SerializeToString()

    assert ipc_rules.read_net_classes(board) == []

    send.assert_called_once()
    request, response_type = send.call_args.args
    assert request.DESCRIPTOR.full_name == 'kiapi.common.commands.GetNetClasses'
    assert request.project.name == 'PCB project avec espaces'
    assert request.project.path == os.path.join(os.path.normpath(path), '')
    assert request.project.path.endswith(os.sep)
    assert response_type is project_commands_pb2.NetClassesResponse
    assert board.document.SerializeToString() == before
    board.get_project.assert_not_called()


@pytest.mark.parametrize(('name', 'path_kind'), [
    ('', 'absolute'), ('PCB', 'empty'), ('', 'empty'),
    ('PCB', 'relative'), ('PCB', 'dot'), ('PCB', 'drive-relative'),
])
def test_missing_or_relative_project_identity_is_refused_before_send(tmp_path, name, path_kind):
    paths = {'absolute': str(tmp_path), 'empty': '', 'relative': 'boards/subfolder',
             'dot': '.', 'drive-relative': 'C:relative-board'}
    board, send = make_board(paths[path_kind], name)
    before = board.document.SerializeToString()
    with pytest.raises(RuntimeError):
        ipc_rules.read_net_classes(board)
    send.assert_not_called()
    assert board.document.SerializeToString() == before


def test_private_request_does_not_change_sdk_global_descriptor(tmp_path):
    global_descriptor = project_commands_pb2.GetNetClasses.DESCRIPTOR
    assert len(global_descriptor.fields) == 0  # Pinned SDK 0.8 wire request.
    assert descriptor_pool.Default().FindMessageTypeByName(
        'kiapi.common.commands.GetNetClasses') is global_descriptor
    board, send = make_board(str(tmp_path))
    ipc_rules.read_net_classes(board)
    request = send.call_args.args[0]
    assert request.DESCRIPTOR is not global_descriptor
    assert 'project' in request.DESCRIPTOR.fields_by_name
    assert len(project_commands_pb2.GetNetClasses.DESCRIPTOR.fields) == 0
    assert project_commands_pb2.GetNetClasses().SerializeToString() == b''


def test_response_uses_sdk_net_classes_without_changing_nanometre_values(tmp_path):
    response = class_response()
    board, _send = make_board(str(tmp_path), response=response)
    classes = ipc_rules.read_net_classes(board)
    assert all(isinstance(cls, NetClass) for cls in classes)
    assert [(cls.name, cls.priority) for cls in classes] == [
        ('Default', 2147483647), ('Power class', 7)]
    default, sparse = classes
    assert {name: getattr(default, name) for name in (
        'clearance', 'track_width', 'diff_pair_track_width', 'diff_pair_gap',
        'diff_pair_via_gap', 'via_diameter', 'via_drill',
        'microvia_diameter', 'microvia_drill')} == {
            'clearance': 225000, 'track_width': 310000,
            'diff_pair_track_width': 170000, 'diff_pair_gap': 180000,
            'diff_pair_via_gap': 0, 'via_diameter': 650000, 'via_drill': 325000,
            'microvia_diameter': 275000, 'microvia_drill': 125000}
    assert sparse.clearance is None and sparse.via_diameter is None


def test_api_failure_propagates_without_unscoped_retry(tmp_path):
    board, send = make_board(str(tmp_path))
    error = ApiError('the requested project is not open')
    send.side_effect = error
    with pytest.raises(ApiError) as caught:
        ipc_rules.read_net_classes(board)
    assert caught.value is error
    send.assert_called_once()
    board.get_project.assert_not_called()


def configure_project_reads(board, monkeypatch):
    def message(name):
        return GetMessageClass(ipc_rules.protocol().FindMessageTypeByName(
            'kiapi.board.commands.' + name))()
    rules = message('BoardDesignRulesResponse')
    rules.rules.constraints.min_clearance.value_nm = 175000
    rules.rules.constraints.min_track_width.value_nm = 190000
    rules.rules.constraints.hole_to_hole_min.value_nm = 0
    custom = message('CustomRulesResponse')
    custom.status = 1
    monkeypatch.setattr(ipc_rules, 'read_rules',
                        lambda _board, custom=False: custom_rules if custom else rules)
    custom_rules = custom
    checked = Mock(return_value='(version 1)\n')
    monkeypatch.setattr(ipc_rules, 'checked_custom_rules', checked)
    nets = [SimpleNamespace(name='/DATA'), SimpleNamespace(name='/PWR')]
    implicit = project_settings_pb2.NetClass(
        name='Default,Power class', type=project_settings_pb2.NCT_IMPLICIT,
        constituents=['Default', 'Power class'])
    explicit = project_settings_pb2.NetClass(name='Default', type=project_settings_pb2.NCT_EXPLICIT)
    board.get_nets = Mock(return_value=nets)
    board.get_netclass_for_nets = Mock(return_value={
        '/DATA': NetClass(explicit), '/PWR': NetClass(implicit)})
    return checked, nets


def test_project_snapshot_keeps_class_values_units_and_effective_assignments(tmp_path, monkeypatch):
    board, send = make_board(str(tmp_path), response=class_response())
    checked, nets = configure_project_reads(board, monkeypatch)
    project, dru = ipc_rules.project_settings(board)
    assert project == {
        'board': {'design_settings': {'rules': {
            'min_clearance': .175, 'min_track_width': .19, 'min_hole_to_hole': 0.}}},
        'net_settings': {
            'classes': [
                {'name': 'Default', 'priority': 2147483647, 'clearance': .225,
                 'track_width': .31, 'via_diameter': .65, 'via_drill': .325,
                 'microvia_diameter': .275, 'microvia_drill': .125,
                 'diff_pair_width': .17, 'diff_pair_gap': .18, 'diff_pair_via_gap': 0.},
                {'name': 'Power class', 'priority': 7}],
            'netclass_assignments': {'/DATA': ['Default'], '/PWR': ['Default', 'Power class']}}}
    assert dru == '(version 1)\n'
    send.assert_called_once()
    board.get_project.assert_not_called()
    board.get_netclass_for_nets.assert_called_once_with(nets)
    checked.assert_called_once()


def test_project_snapshot_does_not_substitute_default_rules_after_api_failure(tmp_path, monkeypatch):
    board, send = make_board(str(tmp_path))
    checked, _nets = configure_project_reads(board, monkeypatch)
    error = ApiError('project identity rejected')
    send.side_effect = error
    with pytest.raises(ApiError) as caught:
        ipc_rules.project_settings(board)
    assert caught.value is error
    send.assert_called_once()
    board.get_project.assert_not_called()
    board.get_netclass_for_nets.assert_not_called()
    checked.assert_not_called()
