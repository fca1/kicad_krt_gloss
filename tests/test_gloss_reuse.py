"""Fast tests for data reuse, changed regions and cooperative execution."""

from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock

import numpy as np
import pytest
from kicad_krt_gloss.runtime import configure_krt_runtime

configure_krt_runtime()

from kicad_parser import Segment
from dgloss.search_cache import SearchCache
from dgloss.execution import GlossSession, perf_counter
from dgloss import pipeline
from dgloss import zone_models as fills


def track(x, net=1):
    return Segment(x, 0, x + 1, 0, .2, "F.Cu", net)


def test_failed_search_reused_until_nearby_or_own_copper_changes():
    source = [track(0)]
    cache = SearchCache(SimpleNamespace(zones=[]), SimpleNamespace(clearance=.2))
    key, reused = cache.token("tracks", 1, source, ())
    assert not reused
    cache.remember_failure(key, source)
    cache.changed([track(100, 2)])
    assert cache.token("tracks", 1, source, ())[1]
    cache.changed([track(.5, 2)])
    assert not cache.token("tracks", 1, source, ())[1]
    cache.remember_failure(key, source)
    cache.changed([track(100, 1)])
    assert not cache.token("tracks", 1, source, ())[1]


def test_remote_change_in_own_zone_invalidates_electrical_certificate():
    zone = SimpleNamespace(net_id=1, polygon=[(0, 0), (200, 0), (200, 20), (0, 20)])
    source = [track(0)]
    cache = SearchCache(SimpleNamespace(zones=[zone]), SimpleNamespace(clearance=.2))
    key, _ = cache.token("tracks", 1, source, ())
    cache.remember_failure(key, source)
    cache.changed([track(100, 2)])
    assert not cache.token("tracks", 1, source, ())[1]


def test_fill_largest_component_is_computed_once(monkeypatch):
    original = fills.krt.ZoneFillModel.__new__(fills.krt.ZoneFillModel)
    original.ok, original._n = True, 2
    original.labels = np.array([[1, 2], [2, 0]])
    model = fills.CachedZoneModel(original)
    count = Mock(wraps=np.bincount)
    monkeypatch.setattr(np, "bincount", count)
    assert model.largest_component() == model.largest_component() == 2
    assert count.call_count == 1


def test_fill_invalidation_keeps_distant_and_same_net_copper(monkeypatch):
    zone = SimpleNamespace(net_id=1, layer="F.Cu", clearance=.2)
    model = SimpleNamespace(ok=True, x0=0, y0=0, nx=100, ny=100, cell=.1)
    key = (1, "F.Cu", id(zone))
    pcb = SimpleNamespace(zones=[zone], _plane_fill_models={key: model})
    registry = {id(zone): model}
    monkeypatch.setattr(fills.krt, "_MODELS_BY_ZONE_ID", registry)
    assert fills.invalidate_copper_models(pcb, [track(1, 1), track(100, 2)]) == set()
    assert pcb._plane_fill_models[key] is model
    assert fills.invalidate_copper_models(pcb, [track(1, 2)]) == {1}
    assert not pcb._plane_fill_models and not registry


def test_local_adapter_is_shared_by_all_krt_lookup_paths(monkeypatch):
    zone = SimpleNamespace(net_id=1, layer="F.Cu", clearance=.2,
                           polygon=[(0, 0), (10, 0), (10, 10)])
    pcb = SimpleNamespace(zones=[zone])
    original = SimpleNamespace(ok=True, x0=0, y0=0, nx=100, ny=100, cell=.1,
                               largest_component=Mock(return_value=3),
                               query_component=Mock(return_value=3))
    factory = Mock(return_value=original)
    monkeypatch.setattr(fills.krt, "ZoneFillModel", factory)
    monkeypatch.setattr(fills.krt, "_MODELS_BY_ZONE_ID", {})
    getter = fills.krt.get_zone_model
    fills.prepare_zone_models(pcb, [zone])
    model = getter(pcb, zone)
    assert isinstance(model, fills.CachedZoneModel)
    assert fills.krt.lookup_zone_model(zone) is model
    assert fills.krt.get_fill_models(pcb, 1)["F.Cu"][0] is model
    fills.prepare_zone_models(pcb, [zone])
    assert getter(pcb, zone) is model
    assert factory.call_count == 1
    assert fills.krt.get_zone_model is getter  # no module-level replacement
    assert model.largest_component() == model.largest_component() == 3
    assert original.largest_component.call_count == 1
    assert model.query_component(1, 1) == 3
    assert fills.invalidate_copper_models(pcb, [track(1, 2)]) == {1}
    assert fills.krt.lookup_zone_model(zone) is None
    fills.prepare_zone_models(pcb, [zone])
    rebuilt = getter(pcb, zone)
    assert rebuilt is not model
    assert factory.call_count == 2
    assert rebuilt.largest_component() == 3
    assert original.largest_component.call_count == 2


def test_local_adapter_does_not_replace_unsupported_models(monkeypatch):
    zone = SimpleNamespace(net_id=1, layer="F.Cu", polygon=[(0, 0), (1, 0), (0, 1)])
    unsupported = SimpleNamespace(ok=False)
    factory = Mock(return_value=unsupported)
    monkeypatch.setattr(fills.krt, "ZoneFillModel", factory)
    monkeypatch.setattr(fills.krt, "_MODELS_BY_ZONE_ID", {})
    pcb = SimpleNamespace(zones=[zone])
    fills.prepare_zone_models(pcb, [zone])
    assert fills.krt.get_zone_model(pcb, zone) is None
    assert pcb._plane_fill_models[(1, "F.Cu", id(zone))] is unsupported
    assert factory.call_count == 1


def test_local_adapter_preserves_krt_model_error_fallback(monkeypatch):
    zone = SimpleNamespace(polygon=[(0, 0), (1, 0), (0, 1)])
    getter = Mock(side_effect=RuntimeError("unsupported model"))
    monkeypatch.setattr(fills.krt, "get_zone_model", getter)
    fills.prepare_zone_models(SimpleNamespace(), [zone])
    getter.assert_called_once()


def test_session_pauses_and_resumes_without_publishing_partial_geometry(monkeypatch):
    entered = Event()
    passed = Event()
    original = track(0)
    pcb = SimpleNamespace(segments=[original], vias=[])

    def run(results, private_pcb, *args, **kwargs):
        private_pcb.segments = []
        entered.set()
        perf_counter()
        passed.set()
        return SimpleNamespace(stats={"g5_valid": True})

    monkeypatch.setattr(pipeline, "run_final_gloss", run)
    session = GlossSession(pcb, None)
    session.control.pause()
    session.start()
    assert entered.wait(1)
    assert not passed.wait(.05)
    assert pcb.segments == [original]
    session.control.resume()
    assert session.done.wait(1)
    assert passed.is_set() and session.result()[1].stats["g5_valid"]
    assert session.control.paused_seconds >= .04
    assert pcb.segments == [original]


def test_session_cancel_unblocks_pause_and_discards_transaction(monkeypatch):
    entered = Event()
    pcb = SimpleNamespace(segments=[track(0)], vias=[])

    def run(results, private_pcb, *args, **kwargs):
        private_pcb.segments = []
        entered.set()
        perf_counter()
        raise AssertionError("cancel must interrupt the search")

    monkeypatch.setattr(pipeline, "run_final_gloss", run)
    session = GlossSession(pcb, None)
    session.control.pause()
    session.start()
    assert entered.wait(1)
    session.control.cancel()
    assert session.done.wait(1)
    assert session.result() is None
    assert len(pcb.segments) == 1
