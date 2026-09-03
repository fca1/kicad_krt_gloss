"""Debug-layer selection and CLI rendering tests without pcbnew."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kicad_krt_gloss.runtime import configure_krt_runtime

configure_krt_runtime()

from kicad_krt_gloss.debug_overlay import (LAYER_NAME, choose_user_layer,
                                            write_cli_debug_overlay)
from kicad_parser import Segment


def test_layer_policy_reuses_owned_layer_before_a_lower_free_layer():
    names = {"User.1": "User.1", "User.2": "Notes",
             "User.3": LAYER_NAME}
    assert choose_user_layer(names, {"User.2", "User.3"}) == "User.3"


def test_layer_policy_uses_first_free_layer_and_protects_named_layers():
    names = {"User.1": "Measurements", "User.2": "User.2",
             "User.3": "User.3"}
    assert choose_user_layer(names, {"User.3"}) == "User.2"
    try:
        choose_user_layer(names, {"User.3"}, "User.1")
    except ValueError as exc:
        assert "already in use" in str(exc)
    else:
        raise AssertionError("an occupied user layer was accepted")


def test_explicit_layer_is_not_redirected_to_an_existing_owned_layer():
    names = {"User.1": LAYER_NAME, "User.2": "User.2"}
    assert choose_user_layer(names, {"User.1"}, "User.2") == "User.2"


def test_cli_replaces_a_previous_gloss_overlay(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text(
        '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (39 "User.1" user)
    (41 "User.2" user "TrackGloss Changes")
  )
  (gr_line
    (start 0 0) (end 1 1)
    (stroke (width 0.1) (type solid))
    (layer "User.2")
  )
)''', encoding="utf-8")
    old = Segment(1.0, 1.0, 3.0, 1.0, 0.2, "F.Cu", 1)
    new = Segment(1.0, 1.0, 2.0, 2.0, 0.2, "F.Cu", 1)
    selected = write_cli_debug_overlay(
        str(board), {"segments": [{"old": old, "new": new}], "vias": []},
        requested="auto")
    content = board.read_text(encoding="utf-8")
    assert selected == "User.2"
    assert content.count('user "TrackGloss Changes"') == 1
    assert content.count('(layer "User.2")') > 1
    assert "(end 1 1)" not in content


def test_cli_auto_uses_the_first_free_layer(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text(
        '''(kicad_pcb
  (version 20240108)
  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (39 "User.1" user "Measurements")
    (41 "User.2" user)
  )
)''', encoding="utf-8")
    old = Segment(0.0, 0.0, 2.0, 0.0, 0.2, "F.Cu", 1)
    new = Segment(0.0, 0.0, 1.0, 1.0, 0.2, "F.Cu", 1)
    selected = write_cli_debug_overlay(
        str(board), {"segments": [{"old": old, "new": new}], "vias": []})
    assert selected == "User.2"
    assert '(41 "User.2" user "TrackGloss Changes")' in board.read_text(
        encoding="utf-8")


def test_cli_empty_result_removes_a_previous_overlay(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text(
        '''(kicad_pcb
  (version 20240108)
  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (39 "User.1" user "TrackGloss Changes")
  )
  (gr_line
    (start 0 0) (end 1 1)
    (stroke (width 0.1) (type solid))
    (layer "User.1")
  )
)''', encoding="utf-8")
    selected = write_cli_debug_overlay(
        str(board), {"segments": [], "vias": []})
    content = board.read_text(encoding="utf-8")
    assert selected == "User.1"
    assert '(layer "User.1")' not in content
    assert 'user "TrackGloss Changes"' in content


def test_cli_explicit_layer_moves_the_owned_overlay(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text(
        '''(kicad_pcb
  (version 20240108)
  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (39 "User.1" user "TrackGloss Changes")
    (41 "User.2" user)
  )
  (gr_line
    (start 0 0) (end 1 1)
    (stroke (width 0.1) (type solid))
    (layer "User.1")
  )
)''', encoding="utf-8")
    old = Segment(0.0, 0.0, 2.0, 0.0, 0.2, "F.Cu", 1)
    new = Segment(0.0, 0.0, 1.0, 1.0, 0.2, "F.Cu", 1)
    selected = write_cli_debug_overlay(
        str(board), {"segments": [{"old": old, "new": new}], "vias": []},
        requested="User.2")
    content = board.read_text(encoding="utf-8")
    assert selected == "User.2"
    assert '(39 "User.1" user)' in content
    assert '(41 "User.2" user "TrackGloss Changes")' in content
    assert '(layer "User.1")' not in content
    assert '(layer "User.2")' in content
