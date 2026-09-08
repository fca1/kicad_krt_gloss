"""Outcome ownership and complete rollback of a detached copper transaction."""

from dataclasses import dataclass, field
from .zone_models import reset_copper_models


@dataclass
class GlossOutcome:
    input_strip_segments: list = field(default_factory=list)
    input_strip_vias: list = field(default_factory=list)
    # Complete mutation history, used to resolve chained via moves.
    changes: dict = field(default_factory=lambda: {
        "segments": [], "vias": [], "doors": []})
    # Strict post-smooth -> final delta, intended only for visualisation.
    visual_changes: dict = field(
        default_factory=lambda: {"segments": [], "vias": [], "doors": []})
    stats: dict = field(default_factory=dict)


def _result_snapshot(results):
    return [(result, list(result.get("new_segments") or []),
             list(result.get("new_vias") or [])) for result in results]


def _restore(results, count, snapshot, pcb_data, segments, vias):
    pcb_data.segments = segments
    pcb_data.vias = vias
    del results[count:]
    for result, result_segments, result_vias in snapshot:
        result["new_segments"] = result_segments
        result["new_vias"] = result_vias
    reset_copper_models(pcb_data)
    pcb_data._gloss_reference_grades = {}
    pcb_data._gloss_views = None
    if hasattr(pcb_data, "_foreign_seg_arr_cache"):
        pcb_data._foreign_seg_arr_cache = None
