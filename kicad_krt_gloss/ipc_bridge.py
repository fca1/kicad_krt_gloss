"""External-process KiCad bridge. All live board access is through IPC.

KRT reads a private snapshot including live project rules. No source save,
SWIG objects, net-code assumptions, or selection changes are used here.
"""
from collections import defaultdict
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile

from .ipc_rules import project_settings


def _uid(item):
    return item.id.value


def _segment_key(segment):
    return (frozenset(((round(segment.start_x, 6), round(segment.start_y, 6)),
                      (round(segment.end_x, 6), round(segment.end_y, 6)))),
            segment.layer, segment.net_id, round(segment.width, 6))


class IpcBoardBridge:
    def __init__(self, client):
        self.client = client
        self.board = client.get_board()
        self.temporary = tempfile.TemporaryDirectory(prefix='krg-ipc-')
        self.path = Path(self.temporary.name) / 'snapshot.kicad_pcb'
        self.data = None
        self._initial_import_active = False
        self._initial_data = None

    def close(self):
        self.temporary.cleanup()

    def active_board(self):
        return self.board

    def refresh(self):
        pass  # IPC commit publication refreshes the editor.

    @contextmanager
    def initial_import(self):
        """Share the initial import only until Run returns, before the event loop.

        Selection inspection, dialog preparation and initial branch capture read
        the same snapshot. Later dialog actions always import again. Publication
        still verifies the live state, including for the direct single-net run.
        """
        if self._initial_import_active:
            raise RuntimeError('IPC opening is already in progress')
        self._initial_import_active = True
        self._initial_data = None
        try:
            yield
        finally:
            self._initial_data = None
            self._initial_import_active = False

    def _state(self):
        project, dru = project_settings(self.board)
        return self.board.get_as_string(), json.dumps(project, sort_keys=True), dru

    def build_pcb_data(self, board):
        if self._initial_import_active and self._initial_data is not None:
            return self._initial_data
        from dgloss.krt_api import parse_kicad_pcb
        from .ipc_snapshot import normalize_snapshot
        state = self._state()
        self.path.write_text(normalize_snapshot(state[0]), encoding='utf-8')
        self.path.with_suffix('.kicad_pro').write_text(state[1], encoding='utf-8')
        self.path.with_suffix('.kicad_dru').write_text(state[2], encoding='utf-8')
        data = parse_kicad_pcb(str(self.path))
        self.net_ids = {net.name: code for code, net in data.nets.items()}
        self.tracks = board.get_tracks()
        self.vias = board.get_vias()
        # Reject a torn import (including changes made while the snapshot was read).
        if self._state() != state:
            raise RuntimeError('Board or rules changed during IPC import; retry Gloss')
        self.state, self.data = state, data
        self.import_index = self.branch_track_index(board, data)
        if self._initial_import_active:
            self._initial_data = data
        return data

    def _track_key(self, track):
        from kipy.util.board_layer import canonical_name
        return (frozenset(((round(track.start.x / 1e6, 6), round(track.start.y / 1e6, 6)),
                           (round(track.end.x / 1e6, 6), round(track.end.y / 1e6, 6)))),
                canonical_name(track.layer), self.net_ids.get(track.net.name),
                round(track.width / 1e6, 6))

    def branch_track_index(self, board, data):
        from kipy.board_types import Track
        buckets = defaultdict(list)
        for segment in data.segments:
            if not getattr(segment, 'graphic', False):
                buckets[_segment_key(segment)].append(segment)
        return {_uid(track): buckets[self._track_key(track)][0] for track in self.tracks
                if isinstance(track, Track) and len(buckets[self._track_key(track)]) == 1}

    def selected_net_names(self, board):
        from kipy.board_types import Track
        return {track.net.name for track in board.get_selection() if isinstance(track, Track)}

    def selected_net_ids(self, board):
        if self.data is None or (self._initial_import_active and self._initial_data is None):
            self.build_pcb_data(board)
        return sorted(self.net_ids[name] for name in self.selected_net_names(board)
                      if name in self.net_ids and self.net_ids[name])

    def selected_seed_segments(self, board, data):
        from kipy.board_types import Track
        index = self.branch_track_index(board, data)
        selected = [_uid(item) for item in board.get_selection() if isinstance(item, Track)]
        if any(uid not in index for uid in selected):
            raise RuntimeError('Selected tracks changed or are ambiguous; import again')
        return [index[uid] for uid in selected]

    def native_arc_net_ids(self, board):
        from kipy.board_types import ArcTrack
        return sorted({self.net_ids[item.net.name] for item in self.tracks
                       if isinstance(item, ArcTrack) and item.net.name in self.net_ids})

    def capture_branches(self, board, data, index, allowed_names):
        from dgloss.branches import elementary_branch_segment_ids
        from .branch_selection_prototype import Branch, StaleBranches
        reverse = {id(segment): uid for uid, segment in index.items()}
        incoming, covered = defaultdict(list), set()
        for seed in self.selected_seed_segments(board, data):
            name = data.nets[seed.net_id].name
            if name not in allowed_names or id(seed) in covered:
                continue
            ids, _ = elementary_branch_segment_ids(data, [seed])
            if not ids <= reverse.keys():
                raise StaleBranches(f'{name}: branch has unmapped copper; import cancelled')
            covered.update(ids)
            points = {(round(x, 6), round(y, 6)) for s in data.segments if id(s) in ids
                      for x, y in ((s.start_x, s.start_y), (s.end_x, s.end_y))}
            vias = frozenset(_uid(v) for v in self.vias if v.net.name == name and
                             (round(v.position.x / 1e6, 6), round(v.position.y / 1e6, 6)) in points)
            incoming[name].append(Branch(frozenset(reverse[i] for i in ids), vias))
        return dict(incoming)

    @staticmethod
    def net_highlighter(board):
        return lambda names: None

    @staticmethod
    def branch_highlighter(board, memory):
        return lambda names, enabled=True: None

    def build_krt_config(self, board, pcb_data, grid_step, net_ids=None):
        from dgloss.krt_api import DesignRules, GridRouteConfig
        from dgloss.rules import install_gloss_rules
        rules = DesignRules.from_project(pcb_data, str(self.path))
        config = GridRouteConfig(
            track_width=rules.class_value(0, 'track_width') or .1,
            clearance=rules.class_value(0, 'clearance') or .1,
            via_size=rules.class_value(0, 'via_diameter') or .3,
            via_drill=rules.class_value(0, 'via_drill') or .2,
            grid_step=float(grid_step), layers=list(pcb_data.board_info.copper_layers),
            board_edge_clearance=rules.board_min.get('min_copper_edge_clearance', 0.),
            hole_to_hole_clearance=rules.board_min.get('min_hole_to_hole'))
        clearances = {n: rules.class_value(n, 'clearance') or config.clearance
                      for n in pcb_data.nets if n}
        routed = sorted(net_ids or clearances)
        config.set_net_clearances(clearances, routed)
        install_gloss_rules(config, pcb_data, routed, source_path=str(self.path), rules=rules)
        return config

    def apply_outcome(self, board, results, outcome):
        from kipy.board_types import Track, Net
        from kipy.geometry import Vector2
        from kipy.util.board_layer import layer_from_canonical_name
        from dgloss.krt_api import mm_to_iu
        if not outcome.stats.get('g5_valid'):
            raise RuntimeError('Refusing an uncertified Gloss result')
        if self._state() != self.state:
            raise RuntimeError('Board or rules changed during Gloss; result discarded')
        index = self.import_index
        native = {_uid(t): t for t in self.tracks}
        by_segment = {id(s): native[uid] for uid, s in index.items()}
        remove = [by_segment[id(s)] for s in
                  {id(s): s for s in outcome.input_strip_segments}.values()]
        created = []
        for result in results:
            for segment in result.get('new_segments') or []:
                item = Track()
                item.start = Vector2.from_xy(mm_to_iu(segment.start_x), mm_to_iu(segment.start_y))
                item.end = Vector2.from_xy(mm_to_iu(segment.end_x), mm_to_iu(segment.end_y))
                item.width = mm_to_iu(segment.width)
                item.layer = layer_from_canonical_name(segment.layer)
                item.net = Net(name=self.data.nets[segment.net_id].name)
                created.append(item)
        moved = {}
        via_keys = [(round(v.position.x / 1e6, 6), round(v.position.y / 1e6, 6), v.net.name)
                    for v in self.vias]
        if outcome.changes.get('vias') and len(set(via_keys)) != len(via_keys):
            raise RuntimeError('Ambiguous colocated vias; cannot map a certified via move')
        via_positions = {(round(v.position.x / 1e6, 6), round(v.position.y / 1e6, 6), v.net.name): v
                         for v in self.vias}
        for change in outcome.changes.get('vias', []):
            old, new = change['old'], change['new']
            name = self.data.nets[old.net_id].name
            key = round(old.x, 6), round(old.y, 6), name
            original = via_positions.pop(key)
            # SDK clone() clears the UUID for creation. Updates must retain it.
            via = type(original)(proto=original.proto)
            if (round(via.diameter / 1e6, 6) != round(old.size, 6) or
                    round(via.drill_diameter / 1e6, 6) != round(old.drill, 6)):
                raise RuntimeError('Via padstack differs from the KRT snapshot')
            via.position = Vector2.from_xy(mm_to_iu(new.x), mm_to_iu(new.y))
            moved[_uid(via)] = via
            via_positions[round(new.x, 6), round(new.y, 6), name] = via
        if not remove and not created and not moved:
            return 0, 0, 0, None
        commit = board.begin_commit()
        try:
            if self._state() != self.state:
                raise RuntimeError('Board changed before IPC commit; result discarded')
            actual = board.create_items(created) if created else []
            if len(actual) != len(created) or any(self._track_key(a) != self._track_key(b)
                                                 for a, b in zip(actual, created)):
                raise RuntimeError('KiCad did not create the certified tracks exactly')
            updates = board.update_items(list(moved.values())) if moved else []
            if (len(updates) != len(moved) or {_uid(a) for a in updates} != moved.keys() or any(
                    a.position != moved[_uid(a)].position for a in updates)):
                raise RuntimeError('KiCad did not move the certified vias exactly')
            if remove:
                # kipy.remove_items discards per-item statuses. Deleted items remain
                # visible to reads until push_commit, so check the IPC receipt.
                from kipy.proto.common.commands.editor_commands_pb2 import DeleteItems, DeleteItemsResponse
                request = DeleteItems()
                request.header.document.CopyFrom(board.document)
                request.item_ids.extend(item.id for item in remove)
                reply = board.client.send(request, DeleteItemsResponse)
                if (reply.status != 1 or len(reply.deleted_items) != len(remove) or
                        {r.id.value for r in reply.deleted_items if r.status == 1} !=
                        {_uid(item) for item in remove}):
                    raise RuntimeError('KiCad refused part of the track deletion')
            from .ipc_overlay import add_overlay
            debug_layer = add_overlay(board, outcome.visual_changes)
            board.push_commit(commit, 'KRT Gloss')
        except Exception:
            board.drop_commit(commit)
            raise
        # Request refill after publication; recent editors schedule it asynchronously.
        try:
            if board.get_zones():
                board.refill_zones()
        except Exception as exc:
            raise RuntimeError('Gloss applied, but zone refill failed. Use Undo or refill and DRC.') from exc
        return len(remove), len(actual), len(moved), debug_layer
