"""Standalone KiCad ActionPlugin orchestrating KRT followed by dgloss."""

from contextlib import redirect_stdout
import io
import json
import os
import sys
import traceback

import pcbnew
import wx

from .kicad_bridge import KiCadBoardBridge
from .runtime import configure_krt_runtime, ensure_krt_dependencies
from .settings_dialog import DEFAULTS, GlossSettingsDialog


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KICAD = KiCadBoardBridge()


class KiCadKrtGlossPlugin(pcbnew.ActionPlugin):
    _settings = dict(DEFAULTS)
    _last_log = ""
    _settings_dialog = None

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
        active_dialog = getattr(self, "_settings_dialog", None)
        if active_dialog is not None:
            try:
                if active_dialog.IsShown():
                    active_dialog.Raise()
                    return
            except (AttributeError, RuntimeError):
                self._settings_dialog = None
        board = KICAD.active_board()
        if board is None:
            wx.MessageBox("No PCB board is open.", "KiCad KRT Gloss",
                          wx.OK | wx.ICON_WARNING)
            return
        net_ids = KICAD.selected_net_ids(board)
        parent = wx.GetTopLevelWindows()[0] if wx.GetTopLevelWindows() else None
        values = dict(self.__class__._settings)
        if len(net_ids) != 1:
            prepared = self._prepare_selection(board, parent)
            if prepared is None:
                return
            scope_nets = self._modifiable_net_rows(board, prepared[0])
            preselected_names = {
                prepared[0].nets[net_id].name for net_id in net_ids
                if net_id in prepared[0].nets}

            def run_from_dialog(new_values, selected_names, append_log):
                self.__class__._settings = dict(new_values)
                ready, checked_ids = self._prepare_checked_nets(
                    board, dialog, selected_names)
                if ready is None:
                    return False
                return self._run_gloss(board, dialog, new_values, checked_ids,
                                append_log=append_log, prepared=ready)


            def import_scope_selection():
                return KICAD.selected_net_names(board)

            highlight_names = KICAD.net_highlighter(board)

            # Keep this window top-level; the explicit editor close binding
            # below closes it with the PCB. This does not suppress KiCad's
            # unconditional dirty marking after RunActionPlugin returns.
            dialog = GlossSettingsDialog(
                None, values, len(net_ids), on_gloss=run_from_dialog,
                pcb_data=prepared[0],
                scope_nets=scope_nets,
                preselected_scope_nets=preselected_names,
                initial_log=self.__class__._last_log,
                on_import_scope=import_scope_selection,
                on_net_selection_changed=highlight_names)

            def close_dialog_with_parent(event):
                """Do not leave a modeless plugin window after the PCB editor."""
                if self._settings_dialog is dialog:
                    dialog.Close()
                event.Skip()

            def on_dialog_close(event):
                self.__class__._settings = dialog.values()
                self.__class__._last_log = dialog.log_value()
                self._settings_dialog = None
                highlight_names(())
                if parent is not None:
                    parent.Unbind(wx.EVT_CLOSE, handler=close_dialog_with_parent)
                event.Skip()

            dialog.Bind(wx.EVT_CLOSE, on_dialog_close)
            if parent is not None:
                parent.Bind(wx.EVT_CLOSE, close_dialog_with_parent)
            self._settings_dialog = dialog
            dialog.Show()
            return

        self._run_gloss(board, parent, values, net_ids, show_progress=False)

    def _prepare_checked_nets(self, board, parent, names):
        """Resolve both dialog actions against the same fresh, explicit scope."""
        if not names:
            return None, []
        prepared = self._prepare_selection(board, parent)
        if prepared is None:
            return None, []
        data, seeds = prepared
        chosen = {code for name, code in self._modifiable_net_rows(board, data)
                  if name in names}
        if not chosen:
            return None, []
        # Native tracks designate branches only on their own checked nets.
        # A checked net without native seeds designates its complete copper.
        seeds = [seed for seed in seeds if seed.net_id in chosen]
        seeded = {seed.net_id for seed in seeds}
        seeds.extend(segment for segment in data.segments
                     if segment.net_id in chosen - seeded
                     and not getattr(segment, "graphic", False))
        return (data, seeds), sorted(chosen)

    @staticmethod
    def _modifiable_net_rows(board, pcb_data):
        """Return only nets the shared Gloss scope considers mutable."""
        from dgloss.context import resolve_gloss_scope

        active, _excluded, _reasons = resolve_gloss_scope(
            pcb_data, excluded_net_ids=KICAD.native_arc_net_ids(board))
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
            pcb_data = KICAD.build_pcb_data(board)
            seed_segments = KICAD.selected_seed_segments(board, pcb_data)
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
                   prepared=None, show_progress=True):
        """Run once and retain the same concise statistics shown by KRT."""
        captured = io.StringIO()
        busy_cursor_started = False

        class LogTee:
            encoding = "utf-8"

            def write(self, text):
                captured.write(text)
                try:
                    sys.__stdout__.write(text)
                except Exception:
                    pass
                if append_log is not None:
                    wx.CallAfter(append_log, text)
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
            # The progress dialog owns feedback for multi-net runs.  Keeping a
            # global busy cursor over its modal loop can strand KiCad in a
            # busy state after the worker has already completed.
            if not show_progress:
                wx.BeginBusyCursor()
                busy_cursor_started = True
            with redirect_stdout(LogTee()):
                print("\n=== Track Gloss run ===")
                print("Options: " + json.dumps(dict(DEFAULTS, **values),
                                               sort_keys=True, ensure_ascii=False))
                configure_krt_runtime()
                if not ensure_krt_dependencies(parent):
                    print("Track Gloss cancelled: dependencies are unavailable.")
                    return False
                from dgloss import GlossConfig, run_final_gloss

                if prepared is None:
                    pcb_data = KICAD.build_pcb_data(board)
                    seed_segments = KICAD.selected_seed_segments(board, pcb_data)
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
                logged_net_ids = sorted(net_ids or {
                    segment.net_id for segment in pcb_data.segments if segment.net_id})
                net_labels = ", ".join(repr(pcb_data.nets[n].name)
                                       for n in logged_net_ids if n in pcb_data.nets)
                print("Net labels: " + net_labels)
                config = KICAD.build_krt_config(
                    board, pcb_data, values["grid_step"], net_ids=net_ids)
                gloss_config = GlossConfig(
                    repeat_until_stable=values.get("repeat_until_stable", True),
                    g4_max_passes=int(values.get("g4_max_passes", 1)),
                    stay_in_corridor=values.get("stay_in_corridor", False),
                    move_vias=values.get("move_vias",
                                         values.get("enable_g3_1", True)),
                    budget_seconds=values["budget_seconds"],
                )
                run_kwargs = {
                    "net_ids": net_ids,
                    "excluded_net_ids": KICAD.native_arc_net_ids(board),
                    "seed_segments": seed_segments,
                }
                if show_progress:
                    from dgloss.execution import GlossSession
                    from .progress_dialog import GlossProgressDialog

                    session = GlossSession(
                        pcb_data, config, gloss_config, **run_kwargs)
                    progress = GlossProgressDialog(parent, session)
                    try:
                        session.start()
                        progress.ShowModal()
                    finally:
                        if not session.done.is_set():
                            session.control.cancel()
                        progress.Destroy()
                    completed = session.result()
                    if completed is None:
                        print("Track Gloss cancelled; board unchanged.")
                        return False
                    results, outcome = completed
                else:
                    results = []
                    outcome = run_final_gloss(
                        results, pcb_data, config, gloss_config, **run_kwargs)
                if not outcome.stats.get("g5_valid", False):
                    print("Track Gloss validation failed; board unchanged.")
                    return False
                removed, added, moved, debug_layer = KICAD.apply_outcome(
                    board, results, outcome)
                KICAD.refresh()
                scope = (f"{len(net_ids)} selected net(s)"
                         if net_ids else "all routed nets")
                stats = outcome.stats
                print("\n=== Track Gloss result ===")
                print(f"Scope: {scope}")
                print("Net labels: " + net_labels)
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
            if busy_cursor_started and wx.IsBusy():
                wx.EndBusyCursor()
