from collections import Counter
from types import SimpleNamespace

from kicad_krt_gloss.runtime import configure_krt_runtime
configure_krt_runtime()
from dgloss import algorithm, pipeline
from dgloss.algorithm import _Chain, _segments_for_points
from dgloss.changes import GlossChanges
from tools.auto_gloss import auto_gloss, revisit_chains


def chain(points):
    return _Chain(_segments_for_points(points, 'F.Cu', .2, 1), points, 'F.Cu', .2)


def test_changed_chain_revisited_unaffected_chain_once():
    a = chain([(0, 0), (1, 1), (2, 0)])
    b = chain([(10, 0), (11, 1), (12, 0)])
    replacement = chain([(0, 0), (2, 0)])
    pcb = SimpleNamespace(segments=a.segments + b.segments)
    def original(*args):
        return [a if a.segments[0] in pcb.segments else replacement, b]
    stats = Counter()
    iterator = revisit_chains(original, pcb, 1, None, stats)
    assert next(iterator) is a
    pcb.segments = replacement.segments + b.segments
    assert list(iterator) == [b, replacement]
    assert stats['chains_requeued'] == 1


def test_equal_geometry_does_not_spin():
    a = chain([(0, 0), (1, 1), (2, 0)])
    b = chain([(0, 0), (1, 1), (2, 0)])
    pcb = SimpleNamespace(segments=a.segments)
    stats = Counter()
    iterator = revisit_chains(lambda *args: [a if pcb.segments is a.segments else b],
                              pcb, 1, None, stats)
    assert next(iterator) is a
    pcb.segments = b.segments
    assert list(iterator) == []
    assert stats['repeated_geometry_skipped'] == 1


def test_patch_restored_on_exception():
    chains, shorten = algorithm._scheduled_chains, pipeline.shorten_routes
    try:
        with auto_gloss():
            assert algorithm._scheduled_chains is not chains
            raise RuntimeError('test')
    except RuntimeError:
        pass
    assert algorithm._scheduled_chains is chains
    assert pipeline.shorten_routes is shorten


def test_intermediate_copper_never_exported(monkeypatch):
    old = chain([(0, 0), (1, 1), (2, 0)]).segments
    transient = chain([(0, 0), (1, .5), (2, 0)]).segments
    final = chain([(0, 0), (2, 0)]).segments
    context = SimpleNamespace(pcb_data=SimpleNamespace(segments=list(old)))
    def fake_shorten(context, results):
        context.pcb_data.segments = final
        changes = GlossChanges(segments=[{'old': s} for s in old + transient]
                               + [{'new': s} for s in transient + final])
        return old + transient, transient + final, changes, {}
    monkeypatch.setattr(pipeline, 'shorten_routes', fake_shorten)
    with auto_gloss():
        strips, added, changes, _ = pipeline.shorten_routes(context, [])
    assert strips == old
    assert added == final
    assert changes.segments == [{'old': s} for s in old] + [{'new': s} for s in final]


def test_integrated_scheduler_revisits_and_exports_only_final_copper(monkeypatch):
    from tests.test_local_micro_cleanup import make_example
    from dgloss.context import build_gloss_context
    from dgloss.pipeline import _grade, _validate_final, _certify_g5_copper
    from dgloss.krt_api import calculate_route_length
    example, config, source = make_example([(0., 0.), (0., 2.), (2., 2.), (4., 0.)])
    pcb = example.pcb_data
    context = build_gloss_context(pcb, config, [1])
    grade = _grade(pcb, 1)
    length = calculate_route_length(source)
    middle = chain([(0., 0.), (1., 1.), (3., 1.), (4., 0.)]).segments
    final = chain([(0., 0.), (4., 0.)]).segments
    calls = []
    def replacement(context, current_chain, *args, **kwargs):
        calls.append(current_chain)
        return current_chain.segments, middle if len(calls) == 1 else final
    monkeypatch.setattr(algorithm, '_best_chain_replacement', replacement)
    # Exercise real production scheduling/custody, without the prototype patch.
    strips, added, changes, totals = algorithm.shorten_routes(context, [], net_ids=[1])
    assert len(calls) == 2
    assert {id(s) for s in strips} == {id(s) for s in source}
    assert added == final
    assert pcb.segments == final
    assert totals['segments_removed'] == len(source)
    assert all(item.get('old', item.get('new')) not in middle for item in changes.segments)
    _validate_final(context, {1: grade}, length, changes)
    _certify_g5_copper(context, {1: grade}, changes)
