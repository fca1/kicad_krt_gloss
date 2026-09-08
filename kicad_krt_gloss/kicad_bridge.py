"""Thin KRG boundary for all native KiCad board operations.

KRT remains the source of truth for board import, rules and validation.  This
module only keeps the plugin's use of KiCad's in-process ``pcbnew`` bindings in
one place, so the orchestration can be tested without a live editor.
"""


class KiCadBoardBridge:
    """Adapt native board access without duplicating KRT's responsibilities."""

    def __init__(self, pcbnew_module=None):
        self._pcbnew_module = pcbnew_module

    def _pcbnew(self):
        if self._pcbnew_module is None:
            import pcbnew
            return pcbnew
        return self._pcbnew_module

    def active_board(self):
        """Return the board currently owned by KiCad, if any."""
        return self._pcbnew().GetBoard()

    def refresh(self):
        """Ask KiCad to redraw after a successful native board update."""
        self._pcbnew().Refresh()

    @staticmethod
    def build_pcb_data(board):
        """Delegate native-board import to KRT through the dgloss façade."""
        from dgloss.krt_api import build_pcb_data_from_board
        return build_pcb_data_from_board(board)

    @staticmethod
    def selected_net_ids(board):
        from .selection import selected_net_ids
        return selected_net_ids(board)

    def selected_net_names(self, board):
        """Translate KiCad's current selected tracks into stable net names."""
        selected = set(self.selected_net_ids(board))
        return {net.GetNetname()
                for code, net in board.GetNetsByNetcode().items()
                if code in selected}

    @staticmethod
    def selected_pad_pair_distance_mm(board):
        from .selection import selected_pad_pair_distance_mm
        return selected_pad_pair_distance_mm(board)

    @staticmethod
    def selected_seed_segments(board, pcb_data):
        from .selection import selected_seed_segments
        return selected_seed_segments(board, pcb_data)

    @staticmethod
    def native_arc_net_ids(board):
        from .selection import native_arc_net_ids
        return native_arc_net_ids(board)

    @staticmethod
    def highlight_net_names(board, names):
        from .selection import highlight_net_names
        return highlight_net_names(board, names)

    @staticmethod
    def build_krt_config(board, pcb_data, grid_step, net_ids=None):
        from .board_adapter import build_krt_config
        return build_krt_config(board, pcb_data, grid_step, net_ids=net_ids)

    @staticmethod
    def apply_outcome(board, results, outcome):
        from .board_adapter import apply_gloss
        return apply_gloss(board, results, outcome)
