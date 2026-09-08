"""Transaction boundaries for corridor Gloss followed by Centering."""
import pytest

from test_local_micro_cleanup import make_example
from dgloss import pipeline
from net_queries import calculate_route_length


def prepare(monkeypatch, fail=None, simulate_centering=False):
    context, config, original = make_example([(1., 1.), (3., 1.), (3., 2.99)])
    pcb = context.pcb_data
    calls, deadlines = [], []
    cleanup = pipeline._run_optimization_pass
    center = pipeline.center_interpad_routes
    certify = pipeline._certify_g5_copper

    def clean(*args, **kwargs):
        calls.append('gloss')
        assert args[2].stay_in_corridor is True
        assert args[2].repeat_until_stable is False
        deadlines.append(args[4])
        result = cleanup(*args, **kwargs)
        assert calculate_route_length(pcb.segments) < calculate_route_length(original)
        return result

    def centered(*args, **kwargs):
        calls.append('centering')
        deadlines.append(kwargs['deadline'])
        assert deadlines[0] == deadlines[1]
        if fail == 'centering':
            raise RuntimeError('injected Centering failure')
        result = center(*args, **kwargs)
        if simulate_centering:
            # Exercise transaction completion independently of door geometry.
            result[3]['branches_centered'] = 1
            result[3]['doors_centered'] = 1
        if fail == 'budget':
            monkeypatch.setattr(pipeline, 'perf_counter', lambda: deadlines[0] + 1.)
        return result

    def certified(*args, **kwargs):
        calls.append('certification')
        if fail == 'certification':
            raise RuntimeError('injected G5 failure')
        return certify(*args, **kwargs)

    monkeypatch.setattr(pipeline, '_run_optimization_pass', clean)
    monkeypatch.setattr(pipeline, 'center_interpad_routes', centered)
    monkeypatch.setattr(pipeline, '_certify_g5_copper', certified)
    return pcb, config, original, calls


def test_no_centering_rolls_back_gloss_with_one_shared_deadline(monkeypatch):
    pcb, config, original, calls = prepare(monkeypatch)
    result = pipeline.run_centering([], pcb, config, net_ids=[1],
                                    budget_seconds=2., _emit_log=False)
    assert calls == ['gloss', 'centering']
    assert result.stats['atomic_rollback'] is True
    assert result.stats['rollback_reason'] == 'no_centering'
    assert result.stats['doors_centered'] == 0
    assert result.stats['centering_doors_detected'] == 0
    assert result.stats['centering_candidates_considered'] == 0
    assert result.stats['centering_candidate_rejections'] == {
        'construction': 0, 'passage': 0, 'scope': 0, 'unchanged': 0,
        'grid': 0, 'clearance': 0, 'same_net': 0, 'connectivity': 0,
    }
    assert result.stats['cleanup_saved_mm'] == 0
    assert result.stats['nets_changed'] == 0
    assert all(a is b for a, b in zip(pcb.segments, original))
    assert not result.input_strip_segments


def test_expired_budget_discards_even_partial_centering(monkeypatch):
    pcb, config, original, calls = prepare(monkeypatch, 'budget', simulate_centering=True)
    result = pipeline.run_centering([], pcb, config, net_ids=[1],
                                    budget_seconds=2., _emit_log=False)
    assert result.stats['rollback_reason'] == 'budget'
    assert result.stats['atomic_rollback'] is True
    assert all(a is b for a, b in zip(pcb.segments, original))
    assert calls == ['gloss', 'centering']


def test_certified_already_centered_passage_keeps_preparatory_gloss(monkeypatch):
    pcb, config, original, calls = prepare(monkeypatch)
    center = pipeline.center_interpad_routes
    def satisfied(*args, **kwargs):
        result = center(*args, **kwargs)
        result[3]['doors_already_centered'] = 1
        return result
    monkeypatch.setattr(pipeline, 'center_interpad_routes', satisfied)
    result = pipeline.run_centering([], pcb, config, net_ids=[1], _emit_log=False)
    assert calls == ['gloss', 'centering', 'certification']
    assert result.stats['g5_valid']
    assert result.stats['doors_centered'] == 0
    assert result.stats['doors_already_centered'] == 1
    assert result.stats['cleanup_saved_mm'] > 0


@pytest.mark.parametrize('failure', ['centering', 'certification'])
def test_failure_restores_state_before_gloss(monkeypatch, failure):
    pcb, config, original, calls = prepare(monkeypatch, failure, simulate_centering=True)
    previous = {'new_segments': [original[0]], 'new_vias': []}
    results = [previous]
    vias = list(pcb.vias)
    result = pipeline.run_centering(results, pcb, config, net_ids=[1],
                                    budget_seconds=2., _emit_log=False)
    assert calls[:2] == ['gloss', 'centering']
    assert result.stats.get('centering_errors') == 1
    assert len(pcb.segments) == len(original)
    assert all(a is b for a, b in zip(pcb.segments, original))
    assert pcb.vias == vias
    assert results == [previous]
    assert previous['new_segments'] == [original[0]]
    assert not result.input_strip_segments
