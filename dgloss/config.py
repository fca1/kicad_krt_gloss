"""Configuration owned by dgloss; KRT's routing configuration stays untouched."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GlossConfig:
    """Feature switches for the final gloss, all enabled by default."""

    enable_g3_1: bool = True
    enable_g3_2: bool = True
    enable_g3_3: bool = True
    enable_g3_4: bool = True
    budget_seconds: float = 20.0

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
