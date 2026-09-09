"""Native EB adapter, accessed by orchestration only through KiCadBoardBridge."""
from collections import defaultdict


def track_index(board, data, pcbnew):
    """Match native UUIDs to this import without relying on object lifetimes."""
    from .board_adapter import _native_segment_key, _segment_key
    buckets = defaultdict(list)
    for s in data.segments:
        if not getattr(s, 'graphic', False):
            buckets[_segment_key(s)].append(s)
    result = {}
    for item in board.GetTracks():
        if item.GetClass() != 'PCB_TRACK':
            continue
        matches = buckets.get(_native_segment_key(board, pcbnew, item), [])
        if len(matches) > 1:
            # Do not let ambiguity on an unrelated net block this import.
            # A selected or remembered UUID absent from the index fails closed.
            continue
        if matches:
            result[item.m_Uuid.AsString()] = matches[0]
    return result


def capture(board, data, index, pcbnew, allowed_names):
    from dgloss.branches import elementary_branch_segment_ids
    from .branch_selection_prototype import Branch, StaleBranches
    by_id = {id(s): uid for uid, s in index.items()}
    incoming = defaultdict(list)
    covered = set()
    for track in board.GetTracks():
        if track.GetClass() != 'PCB_TRACK' or not track.IsSelected():
            continue
        seed = index.get(track.m_Uuid.AsString())
        if seed is None:
            raise StaleBranches('Selected track could not be imported; selection unchanged.')
        name = data.nets[seed.net_id].name
        if name not in allowed_names or id(seed) in covered:
            continue
        ids, _count = elementary_branch_segment_ids(data, [seed])
        if not ids <= by_id.keys():
            raise StaleBranches(f'{name}: branch has unmapped copper; import cancelled.')
        covered.update(ids)
        points = {(round(x, 6), round(y, 6)) for s in data.segments if id(s) in ids
                  for x, y in ((s.start_x, s.start_y), (s.end_x, s.end_y))}
        vias = frozenset(item.m_Uuid.AsString() for item in board.GetTracks()
                         if item.GetClass() == 'PCB_VIA' and item.GetNetCode() == seed.net_id
                         and (round(float(pcbnew.ToMM(item.GetPosition().x)), 6),
                              round(float(pcbnew.ToMM(item.GetPosition().y)), 6)) in points)
        incoming[name].append(Branch(frozenset(by_id[i] for i in ids), vias))
    return dict(incoming)


class BranchHighlighter:
    """The same renderer-visible brightening as production, with UUID filtering."""
    def __init__(self, board, refresh, memory):
        self.board, self.refresh, self.memory = board, refresh, memory
        self.owned = set()

    def __call__(self, names, enabled=True):
        names = set(names)
        items = list(self.board.GetTracks())
        items += [p for f in self.board.GetFootprints() for p in f.Pads()]
        items += list(self.board.Zones())
        present = {i.m_Uuid.AsString() for i in items}
        codes = {code: net.GetNetname() for code, net in self.board.GetNetsByNetcode().items()}
        allowed = {}
        for name in names:
            records = self.memory.by_net.get(name) if enabled else None
            if records:
                tracks = set().union(*(r.tracks for r in records))
                allowed[name] = (tracks | set().union(*(r.vias for r in records))
                                 if tracks <= present else set())
            else:
                allowed[name] = None
        owned = set()
        for item in items:
            uid = item.m_Uuid.AsString()
            name = codes.get(item.GetNetCode())
            chosen = name in allowed and (allowed[name] is None or uid in allowed[name])
            if chosen:
                if uid in self.owned or not item.IsBrightened():
                    item.SetBrightened()
                    owned.add(uid)
            elif uid in self.owned:
                item.ClearBrightened()
        self.owned = owned
        self.refresh()



