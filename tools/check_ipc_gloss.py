"""Acceptance on an explicitly identified disposable PCB; never save its source."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
package = types.ModuleType('kicad_krt_gloss')
package.__path__ = [os.environ.get('KRG_TEST_PLUGIN_ROOT', str(ROOT / 'kicad_krt_gloss'))]
sys.modules[package.__name__] = package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--expected-board', type=Path, required=True)
    parser.add_argument('--net', default='/A')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--branches', action='store_true')
    parser.add_argument('--corridor', action='store_true')
    parser.add_argument('--stale-check', action='store_true',
                        help='With --apply, verify rejection after a temporary board edit and Undo it')
    args = parser.parse_args()
    if args.stale_check and not args.apply:
        parser.error('--stale-check requires --apply on a disposable board')
    os.environ['KRG_IPC'] = '1'
    from kipy import KiCad
    from kicad_krt_gloss.runtime import configure_krt_runtime
    configure_krt_runtime()
    from kicad_krt_gloss.ipc_bridge import IpcBoardBridge
    from dgloss import GlossConfig, run_final_gloss
    from dgloss.krt_api import parse_kicad_pcb
    client = KiCad(socket_path=args.socket, timeout_ms=15000)
    bridge = IpcBoardBridge(client)
    board = bridge.board
    # Document identity, not just the window title or basename.
    document_path = Path(board.document.project.path) / board.document.board_filename
    assert document_path.resolve() == args.expected_board.resolve(), board.document
    source_hash = hashlib.sha256(args.expected_board.read_bytes()).hexdigest()
    data = bridge.build_pcb_data(board)
    original = parse_kicad_pcb(str(args.expected_board.resolve()))
    def pads(pcb):
        return sorted((p.component_ref, p.pad_number, round(p.global_x, 6), round(p.global_y, 6),
                       round(p.size_x, 6), round(p.size_y, 6), p.shape)
                      for values in pcb.pads_by_net.values() for p in values)
    assert pads(data) == pads(original), 'IPC snapshot changed pad geometry'
    print('KiCad:', client.get_version(), 'pad geometry matches file:', len(pads(data)))
    before = {t.id.value: t.proto.SerializeToString() for t in board.get_tracks() + board.get_vias()}
    before_graphics = {item.id.value: item.proto.SerializeToString()
                      for item in board.get_shapes() + board.get_groups()}
    fixed = {t.id.value: t.proto.SerializeToString() for t in board.get_tracks() + board.get_vias()
             if t.net.name != args.net}
    net = bridge.net_ids[args.net]
    seeds = []
    memory = None
    if args.branches:
        from kicad_krt_gloss.branch_selection_prototype import BranchMemory
        from dgloss.branches import elementary_branch_segment_ids
        index = bridge.import_index
        native = {t.id.value: t for t in bridge.tracks}
        candidates, covered = [], set()
        for uid, segment in index.items():
            if segment.net_id == net and id(segment) not in covered:
                ids = elementary_branch_segment_ids(data, [segment])[0]
                covered.update(ids)
                candidates.append((len(ids), native[uid]))
        selected = [t for _, t in sorted(candidates, key=lambda pair: pair[0], reverse=True)[:2]]
        board.clear_selection()
        board.add_to_selection(selected)
        memory = BranchMemory()
        incoming = bridge.capture_branches(board, data, index, {args.net})
        memory.import_branches(incoming, add=False)
        seeds = memory.resolve(data, {args.net}, index, enabled=True)
        editable = {uid for branch in incoming.get(args.net, [])
                    for uid in branch.tracks | branch.vias}
        # Protect unselected branches on the same net, not only other nets.
        fixed.update({uid: value for uid, value in before.items() if uid not in editable})
        board.clear_selection()
        print('Remembered branches:', memory.describe({args.net}, True))
    config = bridge.build_krt_config(board, data, .1, [net])
    results = []
    outcome = run_final_gloss(results, data, config,
                             GlossConfig(g4_max_passes=1, stay_in_corridor=args.corridor),
                             net_ids=[net], seed_segments=seeds,
                             excluded_net_ids=bridge.native_arc_net_ids(board))
    assert outcome.stats['g5_valid']
    print('G5 valid; saved mm:', outcome.stats['saved_mm'])
    if args.stale_check:
        from kipy.board_types import Track
        original_track = next(item for item in board.get_tracks() if isinstance(item, Track))
        witness = Track(proto=original_track.proto)  # clone() would clear the update UUID.
        witness.width += 1000  # 1 um; temporary change on the disposable board only.
        commit = board.begin_commit()
        try:
            updated = board.update_items([witness])
            assert len(updated) == 1 and updated[0].width == witness.width
            board.push_commit(commit, 'IPC stale-result validation witness')
        except Exception:
            board.drop_commit(commit)
            raise
        try:
            changed = {t.id.value: t.proto.SerializeToString()
                       for t in board.get_tracks() + board.get_vias()}
            assert changed != before
            try:
                bridge.apply_outcome(board, results, outcome)
            except RuntimeError as error:
                assert 'changed during Gloss' in str(error), error
            else:
                raise AssertionError('A stale Gloss result was accepted')
            assert changed == {t.id.value: t.proto.SerializeToString()
                               for t in board.get_tracks() + board.get_vias()}
        finally:
            assert client.run_action('common.Interactive.undo').status == 1
        assert before == {t.id.value: t.proto.SerializeToString()
                          for t in board.get_tracks() + board.get_vias()}
        print('Stale result rejected without mutation; one Undo restores witness edit')
    if args.apply:
        published = 0
        push_commit = board.push_commit
        def observe_publication(*arguments, **keywords):
            nonlocal published
            reply = push_commit(*arguments, **keywords)
            published += 1
            return reply
        board.push_commit = observe_publication
        try:
            applied = bridge.apply_outcome(board, results, outcome)
            print('Applied:', applied)
            from kipy.board_types import Track
            from kipy.util.board_layer import canonical_name
            after = {t.id.value: t.proto.SerializeToString()
                     for t in board.get_tracks() + board.get_vias()}
            assert all(after.get(uid) == value for uid, value in fixed.items())
            # Compare live copper, not only receipts/counts or the Undo result.
            def segment(net, layer, width, start, end):
                return (net, layer, round(width, 6), tuple(sorted((
                    tuple(round(v, 6) for v in start), tuple(round(v, 6) for v in end)))))
            expected_tracks = sorted(segment(data.nets[s.net_id].name, s.layer, s.width,
                (s.start_x, s.start_y), (s.end_x, s.end_y)) for s in data.segments if not s.graphic)
            actual_tracks = sorted(segment(t.net.name, canonical_name(t.layer), t.width/1e6,
                (t.start.x/1e6, t.start.y/1e6), (t.end.x/1e6, t.end.y/1e6))
                for t in board.get_tracks() if isinstance(t, Track))
            assert actual_tracks == expected_tracks, 'Applied tracks differ from certified geometry'
            expected_vias = sorted((data.nets[v.net_id].name, round(v.x, 6), round(v.y, 6),
                round(v.size, 6), round(v.drill, 6)) for v in data.vias)
            actual_vias = sorted((v.net.name, round(v.position.x/1e6, 6), round(v.position.y/1e6, 6),
                round(v.diameter/1e6, 6), round(v.drill_diameter/1e6, 6)) for v in board.get_vias())
            assert actual_vias == expected_vias, 'Applied vias differ from certified geometry'
            print('Live tracks and vias match the certified geometry at KiCad precision')
            if applied[3] is not None:
                from kicad_krt_gloss.ipc_overlay import GROUP_NAME
                groups = [g for g in board.get_groups() if g.name == GROUP_NAME]
                assert len(groups) == 1 and groups[0].proto.items
                owned = {uid.value for uid in groups[0].proto.items}
                shapes = [s for s in board.get_shapes() if s.id.value in owned]
                assert len(shapes) == len(owned)
                assert all(canonical_name(s.layer) == applied[3] for s in shapes)
                print('Live overlay:', len(shapes), 'shapes in one group on', applied[3])
        finally:
            board.push_commit = push_commit
            if published:
                assert published == 1, 'Gloss published more than one copper transaction'
                reply = client.run_action('common.Interactive.undo')
                assert reply.status == 1, reply
        restored = {t.id.value: t.proto.SerializeToString() for t in board.get_tracks() + board.get_vias()}
        assert restored == before, 'One Undo did not restore the original copper'
        assert before_graphics == {item.id.value: item.proto.SerializeToString()
                                  for item in board.get_shapes() + board.get_groups()}, \
            'One Undo did not restore the original graphics/groups'
        print('One Undo restores all copper UUIDs/properties; outside scope preserved'
              if published else 'No-op preserves all copper')
    assert hashlib.sha256(args.expected_board.read_bytes()).hexdigest() == source_hash
    print('Source unchanged:', source_hash)
    bridge.close()


if __name__ == '__main__':
    main()
