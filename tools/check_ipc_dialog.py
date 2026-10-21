"""Exercise the real IPC/wx dialog on an explicitly identified disposable board.

The fixture must contain /A with at least three elementary branches and /B.
Gloss is applied once and undone once. The source PCB is never saved.
"""
import argparse
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-root', type=Path, required=True)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--expected-board', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    entry_path = args.plugin_root.resolve() / 'ipc_entry.py'
    expected = args.expected_board.resolve()
    assert entry_path.is_file(), entry_path
    assert expected.is_file(), expected
    os.environ['KICAD_API_SOCKET'] = args.socket
    os.environ['KRG_IPC'] = '1'

    import wx
    from kipy import KiCad

    client = KiCad(socket_path=args.socket, timeout_ms=15000)
    board = client.get_board()

    def assert_document(target):
        actual = (Path(target.document.project.path) /
                  target.document.board_filename).resolve()
        assert actual == expected, f'Wrong PCB: {actual}; expected {expected}'

    def copper():
        return {item.id.value: item.proto.SerializeToString()
                for item in board.get_tracks() + board.get_vias()}

    assert_document(board)  # Before even changing the native selection.
    source_hash = hashlib.sha256(expected.read_bytes()).hexdigest()
    board.clear_selection()  # A single selected net would run Gloss immediately.
    before = copper()
    report = {'board': str(expected), 'plugin_root': str(args.plugin_root.resolve()),
              'kicad': str(client.get_version()), 'source_sha256': source_hash,
              'published_commits': 0, 'undone': False, 'exercise_started': False}
    messages, failures = [], []
    original_app, original_message_box = wx.App, wx.MessageBox
    watchdog = None
    application = None

    def message_box(message, caption='', *positional, **keywords):
        messages.append({'caption': str(caption), 'message': str(message)})
        return wx.OK

    def undo_and_check():
        assert_document(board)
        reply = client.run_action('common.Interactive.undo')
        assert reply.status == 1, reply
        report['undone'] = True
        board.clear_selection()
        assert copper() == before, 'One Undo did not restore every copper UUID/property'
        report['copper_restored'] = True

    def exercise():
        dialog = None
        report['exercise_started'] = True
        try:
            assert not report.get('timed_out'), 'Dialog startup exceeded the watchdog'
            assert not messages, messages
            action = sys.modules['_krg_ipc.action_plugin']
            bridge = action.KICAD
            assert_document(bridge.board)
            assert not bridge._initial_import_active and bridge._initial_data is None
            dialogs = [window for window in wx.GetTopLevelWindows()
                       if hasattr(window, '_branch_memory') and hasattr(window, 'notebook')]
            assert len(dialogs) == 1, 'Expected the real modeless Gloss dialog'
            dialog = dialogs[0]
            assert dialog.IsShown()
            report['tabs'] = [dialog.notebook.GetPageText(i)
                              for i in range(dialog.notebook.GetPageCount())]
            assert report['tabs'] == ['General', 'Gloss', 'Log', 'About']
            assert 'pcbnew' not in sys.modules, 'IPC loaded the legacy SWIG module'
            assert not dialog.scope_net_panel.get_selected_nets()
            assert dialog.controls['selection_uses_elementary_branches'].GetValue()
            plugin = inspect.getclosurevars(dialog._on_gloss_callback).nonlocals['self']
            assert plugin._settings_dialog is dialog

            from dgloss.branches import elementary_branch_segment_ids
            data, index = bridge.data, bridge.import_index
            net = bridge.net_ids['/A']
            reverse = {id(segment): uid for uid, segment in index.items()}
            groups = {}
            for uid, segment in index.items():
                if segment.net_id == net:
                    ids, _ = elementary_branch_segment_ids(data, [segment])
                    assert ids <= reverse.keys(), 'Fixture contains unmapped branch copper'
                    groups.setdefault(frozenset(reverse[i] for i in ids), uid)
            branches = sorted(groups, key=lambda ids: (-len(ids), sorted(ids)))
            assert len(branches) >= 3, 'Fixture /A needs a branch outside the selected two'
            first, second = branches[:2]

            def select(uids):
                assert_document(board)
                native = {track.id.value: track for track in board.get_tracks()}
                assert set(uids) <= native.keys(), 'Selected fixture track disappeared'
                board.clear_selection()
                board.add_to_selection([native[uid] for uid in uids])

            def remembered():
                return {record.tracks for record in dialog._branch_memory.by_net.get('/A', [])}

            select([groups[first]])
            dialog._on_import_scope(False)
            assert remembered() == {first}
            assert set(dialog.scope_net_panel.get_selected_nets()) == {'/A'}
            select([groups[second]])
            dialog._on_import_scope(True)
            dialog._on_import_scope(True)
            assert remembered() == {first, second}, 'Add duplicated or lost a branch'
            dialog._on_clear_scope_selection(None)
            assert not dialog._branch_memory.by_net
            assert not dialog.scope_net_panel.get_selected_nets()
            select([groups[first]])
            dialog._on_import_scope(False)
            select([groups[second]])
            dialog._on_import_scope(True)
            assert remembered() == {first, second}
            records = dialog._branch_memory.by_net['/A']
            scope_ids = set().union(*(record.tracks | record.vias for record in records))
            fixed = {uid: value for uid, value in before.items() if uid not in scope_ids}
            same_net_fixed = {track.id.value for track in board.get_tracks()
                              if track.net.name == '/A' and track.id.value not in scope_ids}
            assert same_net_fixed, 'Fixture does not exercise same-net copper outside scope'

            other = next(track for track in board.get_tracks() if track.net.name == '/B')
            select([other.id.value])
            ready, chosen = plugin._prepare_checked_nets(board, dialog, ['/A'])
            assert ready is not None
            current_data, seeds = ready
            assert {current_data.nets[n].name for n in chosen} == {'/A'}
            selected_ids = {id(segment) for segment in seeds}
            seed_uids = {uid for uid, segment in bridge.import_index.items()
                         if id(segment) in selected_ids}
            assert seed_uids == set(first | second), 'Live /B selection replaced remembered /A scope'
            assert remembered() == {first, second}
            report['remembered_branches'] = 2
            report['outside_scope_copper'] = len(fixed)
            report['same_net_outside_scope_tracks'] = len(same_net_fixed)

            original_push = bridge.board.push_commit
            original_apply = bridge.apply_outcome
            original_callback = dialog._on_gloss_callback

            def push(*arguments, **keywords):
                value = original_push(*arguments, **keywords)
                report['published_commits'] += 1
                return value

            def apply(target, results, outcome):
                assert outcome.stats['g5_valid']
                value = original_apply(target, results, outcome)
                report['g5_valid'] = True
                report['saved_mm'] = outcome.stats['saved_mm']
                report['applied'] = list(value)
                return value

            def callback(*arguments, **keywords):
                value = original_callback(*arguments, **keywords)
                report['callback_completed'] = bool(value)
                return value

            bridge.board.push_commit = push
            bridge.apply_outcome = apply
            dialog._on_gloss_callback = callback
            log_start = len(dialog.log_value())
            dialog._on_gloss(None)  # Real callback, worker and modal progress dialog.
            wx.YieldIfNeeded()  # Flush the real CallAfter log writes.
            assert not report.get('timed_out'), 'Gloss exceeded the watchdog'
            assert not messages, messages
            assert report.get('callback_completed') and report.get('g5_valid'), report
            assert report['published_commits'] == 1, report
            assert report['saved_mm'] > 0, 'Fixture /A produced no change'
            log = dialog.log_value()[log_start:]
            assert 'G5 valid: True' in log and 'Tracks replaced:' in log, log
            after = copper()
            assert after != before, 'Gloss reported success without changing copper'
            assert all(after.get(uid) == value for uid, value in fixed.items()), \
                'Gloss changed copper outside the remembered branches'
            report['outside_scope_preserved'] = True
            undo_and_check()
            assert hashlib.sha256(expected.read_bytes()).hexdigest() == source_hash
            report['source_unchanged'] = True
            report['pcbnew_loaded'] = 'pcbnew' in sys.modules
            assert not report['pcbnew_loaded']
        except Exception:
            failures.append(traceback.format_exc())
        finally:
            # Undo only a publication positively observed in this test, never an
            # arbitrary existing editor command. Also covers a post-commit failure.
            if report['published_commits'] == 1 and not report['undone']:
                try:
                    undo_and_check()
                except Exception:
                    failures.append('Cleanup Undo failed:\n' + traceback.format_exc())
            try:
                assert_document(board)
                board.clear_selection()
                assert hashlib.sha256(expected.read_bytes()).hexdigest() == source_hash
            except Exception:
                failures.append('Cleanup failed:\n' + traceback.format_exc())
            if watchdog is not None:
                watchdog.Stop()
            if dialog is not None:
                dialog.Close()
            if application is not None:
                wx.CallAfter(application.ExitMainLoop)

    def make_app(*arguments, **keywords):
        nonlocal application, watchdog
        application = original_app(*arguments, **keywords)
        started = time.monotonic()

        def timeout():
            report['timed_out'] = True
            failures.append('The 30-second wx watchdog expired')
            # The real progress dialog waits for cooperative worker cancellation.
            # It must finish normally so it cannot publish a cancelled result.
            for window in wx.GetTopLevelWindows():
                session = getattr(window, 'session', None)
                if session is not None:
                    session.control.cancel()
            if not report['exercise_started']:
                application.ExitMainLoop()

        def start_exercise():
            if time.monotonic() - started >= 30:
                report['timed_out'] = True
            exercise()

        watchdog = wx.CallLater(30000, timeout)
        wx.CallAfter(start_exercise)
        return application

    wx.App = make_app
    wx.MessageBox = message_box
    try:
        spec = importlib.util.spec_from_file_location('_ipc_dialog_entry', entry_path)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        report['entry_exit_code'] = entry.main()
        if report['entry_exit_code'] != 0 or not report['exercise_started']:
            failures.append('IPC entry did not complete the real dialog exercise')
    except Exception:
        failures.append(traceback.format_exc())
    finally:
        if watchdog is not None:
            watchdog.Stop()
        wx.App, wx.MessageBox = original_app, original_message_box
    report['message_boxes'] = messages
    report['failures'] = failures
    report['passed'] = not failures and not messages and report.get('copper_restored', False)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
