"""Architecture tests that need neither KiCad nor pcbnew."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kicad_krt_gloss.selection import selected_net_ids


class Item:
    def __init__(self, net_id=0, selected=True):
        self.net_id = net_id
        self.selected = selected

    def GetNetCode(self):
        return self.net_id

    def IsSelected(self):
        return self.selected


class Footprint(Item):
    def __init__(self, pads, selected=False):
        super().__init__(0, selected)
        self.pads = pads

    def Pads(self):
        return self.pads


class Board:
    def __init__(self):
        self.tracks = [Item(7), Item(7), Item(8, False)]
        self.footprints = [Footprint([Item(9, False)], selected=True),
                           Footprint([Item(10)], selected=False)]
        self.zones = [Item(11), Item(0)]

    def GetTracks(self):
        return self.tracks

    def GetFootprints(self):
        return self.footprints

    def GetAreaCount(self):
        return len(self.zones)

    def GetArea(self, index):
        return self.zones[index]


def test_selection_filters_every_supported_item_to_unique_complete_net_ids():
    assert selected_net_ids(Board()) == [7, 9, 10, 11]


def test_dgloss_runtime_does_not_depend_on_pcbnew_or_plugin_package():
    for source in (ROOT / "dgloss").glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "pcbnew" not in text, source.name
        assert "kicad_krt_gloss" not in text, source.name
