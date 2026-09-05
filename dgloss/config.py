"""Configuration owned by dgloss; KRT's routing configuration stays untouched."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GlossConfig:
    """Internal feature switches for the final gloss."""

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
    centering_clearance_factor: float = 3.0
    centering_build_new_segments: bool = False
    centering_build_multi_door_path: bool = False

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
