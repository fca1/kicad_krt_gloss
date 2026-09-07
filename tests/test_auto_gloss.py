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
    chains, shorten = algorithm._simple_chains, pipeline.shorten_routes
    try:
        with auto_gloss():
            assert algorithm._simple_chains is not chains
            raise RuntimeError('test')
    except RuntimeError:
        pass
    assert algorithm._simple_chains is chains
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
