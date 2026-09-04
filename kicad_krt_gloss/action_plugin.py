"""Standalone KiCad ActionPlugin orchestrating KRT followed by dgloss."""

from contextlib import redirect_stdout
import io
import os
import sys
import traceback

import pcbnew
import wx

from .runtime import configure_krt_runtime, ensure_krt_dependencies
from .selection import (native_arc_net_ids, selected_net_ids,
                        selected_seed_segments)
from .settings_dialog import DEFAULTS, GlossSettingsDialog
from .version import __version__


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


class KiCadKrtGlossPlugin(pcbnew.ActionPlugin):
    _settings = dict(DEFAULTS)
    _last_log = ""

    def defaults(self):
        self.name = "KiCad KRT Gloss"
        self.category = "Routing"
        self.description = "Apply the KRT-based final gloss to routed nets"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(PLUGIN_DIR, "icon_24.png")
        dark = os.path.join(PLUGIN_DIR, "icon_24_dark.png")
        if os.path.exists(dark):
            self.dark_icon_file_name = dark

    def Run(self):
        board = pcbnew.GetBoard()
        if board is None:
            wx.MessageBox("No PCB board is open.", "KiCad KRT Gloss",
                          wx.OK | wx.ICON_WARNING)
            return
        net_ids = selected_net_ids(board)
        parent = wx.GetTopLevelWindows()[0] if wx.GetTopLevelWindows() else None
        values = dict(self.__class__._settings)
        if len(net_ids) != 1:
            prepared = None
            if net_ids:
                prepared = self._prepare_selection(board, parent)
                if prepared is None:
                    return

            def run_from_dialog(new_values, append_log):
                nonlocal prepared
                self.__class__._settings = dict(new_values)
                ready = prepared
                prepared = None
                self._run_gloss(board, parent, new_values, net_ids,
                                append_log=append_log, prepared=ready)

            dialog = GlossSettingsDialog(
                parent, values, len(net_ids), on_gloss=run_from_dialog,
                initial_log=self.__class__._last_log)
            try:
                dialog.ShowModal()
                values = dialog.values()
                self.__class__._last_log = dialog.log_value()
            finally:
                dialog.Destroy()
            self.__class__._settings = values
            return

        self._run_gloss(board, parent, values, net_ids)

    @staticmethod
    def _prepare_selection(board, parent):
        """Prepare PCB data and selection seeds once for the dialog run."""
        configure_krt_runtime()
        if not ensure_krt_dependencies(parent):
            return None
        try:
            wx.BeginBusyCursor()
            from kicad_parser import build_pcb_data_from_board

            pcb_data = build_pcb_data_from_board(board)
            seed_segments = selected_seed_segments(board, pcb_data)
            return pcb_data, seed_segments
        except Exception:
            wx.MessageBox(
                "Track Gloss could not inspect the current selection.\n\n" +
                traceback.format_exc(),
                "KiCad KRT Gloss — Error", wx.OK | wx.ICON_ERROR)
            return None
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()

    def _run_gloss(self, board, parent, values, net_ids, *, append_log=None,
                   prepared=None):
        """Run once and retain the same concise statistics shown by KRT."""
        captured = io.StringIO()

        class LogTee:
            encoding = "utf-8"

            def write(self, text):
                captured.write(text)
                try:
                    sys.__stdout__.write(text)
                except Exception:
                    pass
                if append_log is not None:
                    append_log(text)
                return len(text)

            def flush(self):
                try:
                    sys.__stdout__.flush()
                except Exception:
                    pass

            @staticmethod
            def isatty():
                return False

        try:
            wx.BeginBusyCursor()
            with redirect_stdout(LogTee()):
                print("\n=== Track Gloss run ===")
                configure_krt_runtime()
                if not ensure_krt_dependencies(parent):
                    print("Track Gloss cancelled: dependencies are unavailable.")
                    return False
                from kicad_parser import build_pcb_data_from_board
                from dgloss import GlossConfig, run_final_gloss
                from .board_adapter import apply_gloss, build_krt_config

                if prepared is None:
                    pcb_data = build_pcb_data_from_board(board)
                    seed_segments = selected_seed_segments(board, pcb_data)
                else:
                    pcb_data, seed_segments = prepared
                use_branches = bool(
                    values["selection_uses_elementary_branches"])
                if not use_branches:
                    seed_segments = []
                if seed_segments:
                    net_ids = sorted({segment.net_id
                                      for segment in seed_segments})
                    print(f"Track Gloss BE: {len(seed_segments)} segment "
                          f"seed(s) on {len(net_ids)} net(s)")
                config = build_krt_config(
                    board, pcb_data, values["grid_step"], net_ids=net_ids)
                gloss_config = GlossConfig(
                    enable_g3_1=values["enable_g3_1"],
                    enable_g3_2=values["enable_g3_2"],
                    enable_g3_3=values["enable_g3_3"],
                    enable_g3_4=values["enable_g3_4"],
                    enable_noncollinear_t_rails=values[
                        "enable_noncollinear_t_rails"],
                    enable_multipasses=values["enable_multipasses"],
                    budget_seconds=values["budget_seconds"],
                )
                results = []
                outcome = run_final_gloss(
                    results, pcb_data, config, gloss_config, net_ids=net_ids,
                    excluded_net_ids=native_arc_net_ids(board),
                    seed_segments=seed_segments)
                removed, added, moved, debug_layer = apply_gloss(
                    board, results, outcome)
                pcbnew.Refresh()
                scope = (f"{len(net_ids)} selected net(s)"
                         if net_ids else "all routed nets")
                stats = outcome.stats
                print("\n=== Track Gloss result ===")
                print(f"Scope: {scope}")
                print(f"Length: {stats.get('before_mm', 0.0):.4f} -> "
                      f"{stats.get('after_mm', 0.0):.4f} mm")
                print(f"Saved: {stats.get('saved_mm', 0.0):.4f} mm")
                print(f"Tracks replaced: {removed} -> {added}")
                print(f"Vias moved: {moved}")
                print(f"G4 passes: {stats.get('g4_passes_completed', 0)}")
                if stats.get("branch_scoped"):
                    print("Elementary branches: "
                          f"{stats.get('elementary_branches', 0)}")
                print(f"G5 valid: {bool(stats.get('g5_valid', False))}")
            if len(net_ids) != 1:
                overlay_note = (
                    f'Differences are shown on {debug_layer} '
                    '("TrackGloss Changes").'
                    if debug_layer else
                    "No free User layer was available for the differences.")
                wx.MessageBox(
                    f"Scope: {scope}\n"
                    f"Saved: {outcome.stats.get('saved_mm', 0.0):.4f} mm\n"
                    f"Tracks replaced: {removed} -> {added}\n"
                    f"Vias moved: {moved}\n\n"
                    f"{overlay_note}\n\n"
                    "The board was modified but not saved.",
                    f"KiCad KRT Gloss {__version__}",
                    wx.OK | wx.ICON_INFORMATION)
            return True
        except Exception:
            detail = traceback.format_exc()
            captured.write(detail)
            if append_log is not None:
                append_log(detail)
            wx.MessageBox(
                "Track Gloss failed; the board was left unchanged whenever "
                "native apply had not started.\n\n" + detail,
                "KiCad KRT Gloss — Error", wx.OK | wx.ICON_ERROR)
            return False
        finally:
            if append_log is None:
                self.__class__._last_log = captured.getvalue()
            if wx.IsBusy():
                wx.EndBusyCursor()
