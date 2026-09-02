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
