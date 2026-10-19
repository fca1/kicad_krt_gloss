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
    args = parser.parse_args()
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
    if args.apply:
        print('Applied:', bridge.apply_outcome(board, results, outcome))
        after = {t.id.value: t.proto.SerializeToString() for t in board.get_tracks() + board.get_vias()}
        assert all(after.get(uid) == value for uid, value in fixed.items())
        if outcome.stats['saved_mm'] > 0:
            reply = client.run_action('common.Interactive.undo')
            assert reply.status == 1, reply
        restored = {t.id.value: t.proto.SerializeToString() for t in board.get_tracks() + board.get_vias()}
        assert restored == before, 'One Undo did not restore the original copper'
        print('One Undo restores all copper UUIDs/properties; outside scope preserved'
              if outcome.stats['saved_mm'] > 0 else 'No-op preserves all copper')
    assert hashlib.sha256(args.expected_board.read_bytes()).hexdigest() == source_hash
    print('Source unchanged:', source_hash)
    bridge.close()


if __name__ == '__main__':
    main()
