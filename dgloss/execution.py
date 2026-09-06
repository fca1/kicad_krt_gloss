"""Cooperative pause/cancel and a detached, transactional Gloss worker."""

from copy import copy
from threading import Condition, Event, Thread, local
from time import perf_counter as _wall_time

_thread = local()


class GlossCancelled(Exception):
    pass


class RunControl:
    def __init__(self):
        self.condition = Condition()
        self.pause_requested = False
        self.paused = False
        self.cancelled = False
        self.paused_seconds = 0.0

    def pause(self):
        with self.condition:
            self.pause_requested = True

    def resume(self):
        with self.condition:
            self.pause_requested = False
            self.condition.notify_all()

    def cancel(self):
        with self.condition:
            self.cancelled = True
            self.condition.notify_all()

    def checkpoint(self):
        with self.condition:
            if self.cancelled:
                raise GlossCancelled("Gloss cancelled; input preserved")
            if self.pause_requested:
                started = _wall_time()
                self.paused = True
                try:
                    while self.pause_requested and not self.cancelled:
                        self.condition.wait()
                finally:
                    self.paused_seconds += _wall_time() - started
                    self.paused = False
            if self.cancelled:
                raise GlossCancelled("Gloss cancelled; input preserved")


def perf_counter():
    """Search clock: pauses do not consume the active optimization budget."""
    control = getattr(_thread, "control", None)
    if control is None:
        return _wall_time()
    control.checkpoint()
    return _wall_time() - control.paused_seconds


class GlossSession:
    """Run on detached Python PCB data; no native KiCad/wx calls in the worker.

    Poll done; pause/resume retain the exact search stack and caches. Cancel
    discards the private transaction. Only a certified outcome may be applied
    by the caller, on the UI thread. The caller must keep input pads/rules fixed.
    """

    def __init__(self, pcb_data, config, gloss_config=None, **kwargs):
        self.control = RunControl()
        self.done = Event()
        self._value = None
        self._error = None
        self.pcb_data = copy(pcb_data)
        self.pcb_data.segments = list(pcb_data.segments)
        self.pcb_data.vias = list(pcb_data.vias)
        self.pcb_data._plane_fill_models = {}
        self.pcb_data._foreign_seg_arr_cache = None
        self._worker = Thread(target=self._run, args=(config, gloss_config, kwargs),
                              name="Gloss search", daemon=True)

    def start(self):
        self._worker.start()
        return self

    def _run(self, config, gloss_config, kwargs):
        from .pipeline import run_final_gloss

        _thread.control = self.control
        results = []
        try:
            outcome = run_final_gloss(results, self.pcb_data, config, gloss_config, **kwargs)
            self._value = results, outcome
        except GlossCancelled:
            # Cancellation before the engine has entered its transaction.
            self._value = None
        except BaseException as exc:
            self._error = exc
        finally:
            del _thread.control
            self.done.set()

    def result(self):
        if not self.done.is_set():
            raise RuntimeError("Gloss is still running")
        if self._error is not None:
            raise self._error
        if self.control.cancelled:
            return None
        return self._value
