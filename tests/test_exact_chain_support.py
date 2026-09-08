"""Chain search must not invent widths, connections, or a 100-track anchor."""
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from kicad_parser import Segment, PCBData, BoardInfo, Net
from dgloss.chain_topology import _simple_chains, _walk_branch_chain
from dgloss.tests.test_g0_g1_g3 import _pad
from dgloss.pad_terminals import _walk_terminal_chain


def board(segments, pads=()):
    return PCBData(BoardInfo({}, ['F.Cu'], (-1, -1, 200, 2)),
                   {1: Net(1, 'A')}, {}, [], segments, {1: list(pads)})


def test_chain_keeps_exact_width_and_stops_at_width_change():
    source = [Segment(i, 0, i+1, 0, .123456789, 'F.Cu', 1) for i in range(3)]
    pcb = board(source)
    assert _simple_chains(pcb, 1)[0].width == .123456789
    source[2].width = .123457
    pcb = board(source)
    assert _simple_chains(pcb, 1)[0].segments == source[:2]
    assert _walk_branch_chain(pcb, 1, (0, 0), source[0])[0] == source[:2]


def test_near_coincident_endpoints_do_not_invent_a_chain():
    source = [Segment(0, 0, 1, 0, .2, 'F.Cu', 1),
              Segment(1.0000001, 0, 2, 0, .2, 'F.Cu', 1)]
    assert _simple_chains(board(source), 1) == []
    assert _walk_branch_chain(board(source), 1, (0, 0), source[0])[0] == source[:1]


def test_pad_and_branch_walks_reach_the_real_anchor_beyond_100_segments():
    source = [Segment(i, 0, i+1, 0, .2, 'F.Cu', 1) for i in range(120)]
    pad = _pad('P', 0, 0, 1, size=.2)
    pcb = board(source, [pad])
    walked, anchor = _walk_branch_chain(pcb, 1, (0, 0), source[0])
    assert walked == source and anchor == (120, 0)
    walked, points = _walk_terminal_chain(pcb, 1, pad)
    assert walked == source and points[-1] == (120, 0)
