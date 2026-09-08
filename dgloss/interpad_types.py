"""Immutable descriptions of centering gates and candidates."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InterpadDoor:
    pad_a: object
    pad_b: object
    segment: object
    layer: str
    crossing: tuple
    axis: tuple
    edge_a: tuple
    edge_b: tuple
    clearance_a: float
    clearance_b: float
    proximity_mm: float
    distance_a: float
    distance_b: float
    copper_gap: float
    admissible_width: float
    offset: float


@dataclass(frozen=True)
class InterpadScan:
    doors: tuple
    elapsed_ms: float
    pad_pairs: int
    geometric_gates: int
    unique_crossings: int


@dataclass(frozen=True)
class InterpadCandidate:
    source_segments: tuple
    segments: tuple
    translation: tuple
    before_length: float
    after_length: float
