"""Change records shared by the gloss and the KiCad visualisation."""

from dataclasses import dataclass, field


@dataclass
class GlossChanges:
    segments: list = field(default_factory=list)
    vias: list = field(default_factory=list)

    def __bool__(self):
        return bool(self.segments or self.vias)

    def as_dict(self):
        return {"segments": self.segments, "vias": self.vias}


def release_result_custody(results, segments=(), vias=()):
    """Remove replaced generated objects and return only native input strips."""
    segment_ids = {id(segment) for segment in segments}
    via_ids = {id(via) for via in vias}
    owned_segments = set()
    owned_vias = set()
    for result in results:
        current_segments = list(result.get("new_segments") or [])
        owned_segments.update(id(segment) for segment in current_segments
                              if id(segment) in segment_ids)
        result["new_segments"] = [segment for segment in current_segments
                                  if id(segment) not in segment_ids]
        current_vias = list(result.get("new_vias") or [])
        owned_vias.update(id(via) for via in current_vias
                          if id(via) in via_ids)
        result["new_vias"] = [via for via in current_vias
                              if id(via) not in via_ids]
    return ([segment for segment in segments
             if id(segment) not in owned_segments],
            [via for via in vias if id(via) not in owned_vias])
