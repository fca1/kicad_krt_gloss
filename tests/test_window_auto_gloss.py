from collections import Counter
from types import SimpleNamespace
from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss import algorithm, GlossConfig
from dgloss.pipeline import run_final_gloss
from tests.test_auto_gloss import chain
from tests.test_local_micro_cleanup import make_example
from tools.window_auto_gloss import affected_windows, revisit_windows, window_auto_gloss


def test_windows_are_bounded_and_cover_new_joint():
    source = chain([(i, 0) for i in range(9)])
    windows = list(affected_windows(source, {('F.Cu', 4, 0)}, set()))
    assert len(windows) == 4
    assert all(len(w.segments) == 3 for w in windows)
    assert all(4 in [p[0] for p in w.points] for w in windows)


def test_only_small_windows_revisited_after_initial_chain():
    source = chain([(0, 0), (1, 1), (2, 0), (3, 1), (4, 0), (5, 1), (6, 0)])
    replacement = chain([(0, 0), (1, .5), (2, 0), (3, .5), (4, 0), (5, .5), (6, 0)])
    pcb = SimpleNamespace(segments=source.segments)
    stats = Counter()
    iterator = revisit_windows(lambda *args: [source if pcb.segments is source.segments else replacement],
                               pcb, 1, None, stats)
    assert next(iterator) is source
    pcb.segments = replacement.segments
    windows = list(iterator)
    assert len(windows) == 4
    assert all(len(w.segments) <= 3 for w in windows)
    assert stats['topology_rebuilds'] == 1


def test_window_boundary_rejects_new_right_angle(monkeypatch):
    window = chain([(0, 0), (1, 1), (2, 1)])
    window.small_window = True
    sibling = chain([(-1, 0), (0, 0)]).segments
    candidate = chain([(0, 0), (0, 1), (2, 1)]).segments
    def fake_best(context, chain, net, foreign, current, vias, **kwargs):
        return kwargs['accept_replacement'](chain.segments, candidate)
    monkeypatch.setattr(algorithm, '_best_chain_replacement', fake_best)
    with window_auto_gloss():
        assert algorithm._best_chain_replacement(None, window, 1, None,
                    window.segments+sibling, [], accept_replacement=lambda *a: True) is False


def test_real_pipeline_krt_certificate_and_patch_restoration():
    example, config, _ = make_example([(0., 0.), (1., 1.), (2., 1.), (3., 0.)])
    original = algorithm._best_chain_replacement
    with window_auto_gloss():
        result = run_final_gloss([], example.pcb_data, config,
            GlossConfig(repeat_until_stable=False, budget_seconds=2.), net_ids=[1])
    assert result.stats['g5_valid'] is True
    assert result.stats['saved_mm'] > .1
    assert algorithm._best_chain_replacement is original
