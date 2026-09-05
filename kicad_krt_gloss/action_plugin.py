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
            prepared = self._prepare_selection(board, parent)
            if prepared is None:
                return
            centering_nets = self._modifiable_net_rows(board, prepared[0])
            preselected_names = {
                prepared[0].nets[net_id].name for net_id in net_ids
                if net_id in prepared[0].nets}

            def run_from_dialog(new_values, append_log):
                nonlocal prepared
                self.__class__._settings = dict(new_values)
                ready = prepared
                prepared = None
                self._run_gloss(board, parent, new_values, net_ids,
                                append_log=append_log, prepared=ready)

            def center_from_dialog(new_values, selected_names, append_log):
                nonlocal prepared
                self.__class__._settings = dict(new_values)
                ready = prepared
                prepared = None
                self._run_centering(
                    board, parent, new_values, selected_names,
                    append_log=append_log, prepared=ready)

            dialog = GlossSettingsDialog(
                parent, values, len(net_ids), on_gloss=run_from_dialog,
                on_centering=center_from_dialog, pcb_data=prepared[0],
                centering_nets=centering_nets,
                preselected_centering_nets=preselected_names,
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
    def _modifiable_net_rows(board, pcb_data):
        """Return only nets the shared Gloss scope considers mutable."""
        from dgloss.context import resolve_gloss_scope

        active, _excluded, _reasons = resolve_gloss_scope(
            pcb_data, excluded_net_ids=native_arc_net_ids(board))
        return [(pcb_data.nets[net_id].name, net_id) for net_id in active
                if net_id in pcb_data.nets and pcb_data.nets[net_id].name]

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
                print("KRT smooth: "
                      f"{stats.get('before_mm', 0.0):.4f} -> "
                      f"{stats.get('krt_after_mm', 0.0):.4f} mm "
                      f"(-{stats.get('krt_baseline_saved_mm', 0.0):.4f} mm)")
                print("Post-KRT stages: "
                      f"-{stats.get('post_krt_saved_mm', 0.0):.4f} mm")
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

    def _run_centering(self, board, parent, values, selected_names, *,
                       append_log=None, prepared=None):
        """Run only G3.6 and keep the settings dialog open."""
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
                print("\n=== Track Gloss Centering run ===")
                configure_krt_runtime()
                if not ensure_krt_dependencies(parent):
                    print("Centering cancelled: dependencies are unavailable.")
                    return False
                from kicad_parser import build_pcb_data_from_board
                from dgloss import run_centering
                from .board_adapter import apply_gloss, build_krt_config

                if prepared is None:
                    pcb_data = build_pcb_data_from_board(board)
                    _seed_segments = selected_seed_segments(board, pcb_data)
                else:
                    pcb_data, _seed_segments = prepared
                names_to_ids = {net.name: net_id
                                for net_id, net in pcb_data.nets.items()}
                net_ids = sorted(names_to_ids[name] for name in selected_names
                                 if name in names_to_ids)
                if not net_ids:
                    print("Centering cancelled: no selected modifiable net remains.")
                    return False
                config = build_krt_config(
                    board, pcb_data, values["grid_step"], net_ids=net_ids)
                results = []
                outcome = run_centering(
                    results, pcb_data, config, net_ids=net_ids,
                    proximity_mm=values["centering_proximity_mm"],
                    build_new_segments=values[
                        "centering_build_new_segments"],
                    build_multi_door_path=values[
                        "centering_build_multi_door_path"],
                    budget_seconds=values["budget_seconds"],
                    excluded_net_ids=native_arc_net_ids(board),
                    seed_segments=(
                        _seed_segments if values[
                            "selection_uses_elementary_branches"] else None))
                removed, added, moved, debug_layer = apply_gloss(
                    board, results, outcome)
                pcbnew.Refresh()
                stats = outcome.stats
                print("\n=== Track Gloss Centering result ===")
                print(f"Scope: {len(net_ids)} selected net(s)")
                print(f"Doors centered: {stats.get('doors_centered', 0)}")
                print("Length delta: "
                      f"{stats.get('centering_length_delta_mm', 0.0):+.4f} mm")
                print(f"Tracks replaced: {removed} -> {added}")
                print(f"G5 valid: {bool(stats.get('g5_valid', False))}")
                if debug_layer:
                    print(f"Differences: {debug_layer} (TrackGloss Changes)")
            return {
                "doors_centered": stats.get("doors_centered", 0),
                "centering_proximity_mm": values[
                    "centering_proximity_mm"],
            }
        except Exception:
            detail = traceback.format_exc()
            captured.write(detail)
            if append_log is not None:
                append_log(detail)
            wx.MessageBox(
                "Centering failed; the board was left unchanged whenever "
                "native apply had not started.\n\n" + detail,
                "KiCad KRT Gloss — Error", wx.OK | wx.ICON_ERROR)
            return False
        finally:
            if append_log is None:
                self.__class__._last_log = captured.getvalue()
            if wx.IsBusy():
                wx.EndBusyCursor()
