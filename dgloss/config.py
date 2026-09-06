"""Configuration owned by dgloss; KRT's routing configuration stays untouched."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GlossConfig:
    """Gloss intentions; numbered switches are legacy diagnostic controls."""

    enable_g3_1: bool = True
    enable_g3_2: bool = True
    enable_g3_3: bool = True
    enable_g3_4: bool = True
    budget_seconds: float = 20.0
    enable_noncollinear_t_rails: bool = True
    enable_multipasses: bool = True
    # G3.6 remains opt-in until its integrated validation is complete.  These
    # settings are intentionally engine/API-only; the KiCad UI does not expose
    # them yet.
    enable_g3_6: bool = False
    centering_proximity_mm: float = 1.0
    centering_build_new_segments: bool = False
    centering_build_multi_door_path: bool = False
    # Prototype restriction for fixed-anchor track shortcuts; opt-in.
    stay_in_corridor: bool = False

    # None migrates existing callers without breaking positional arguments.
    move_vias: bool = None
    optimize_pad_approaches: bool = None
    move_junctions: bool = None
    repeat_until_stable: bool = None

    def __post_init__(self):
        import math
        if not math.isfinite(self.budget_seconds) or self.budget_seconds < 0:
            raise ValueError("budget_seconds must be finite and non-negative")
        for name, legacy in (
                ("move_vias", self.enable_g3_1),
                ("optimize_pad_approaches", self.enable_g3_2),
                ("move_junctions", self.enable_g3_3),
                ("repeat_until_stable", self.enable_multipasses)):
            if getattr(self, name) is None:
                object.__setattr__(self, name, legacy)

    @classmethod
    def from_value(cls, value=None):
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            allowed = cls.__dataclass_fields__
            return cls(**{key: value[key] for key in allowed if key in value})
        return cls(**{key: getattr(value, key)
                     for key in cls.__dataclass_fields__
                     if hasattr(value, key)})

    def as_dict(self):
        return asdict(self)
