"""Structured G3.5 statistics with the same concise output style as KRT."""

from dataclasses import asdict, dataclass, field


@dataclass
class StageStats:
    enabled: bool = True
    changes: int = 0
    saved_mm: float = 0.0
    elapsed_ms: float = 0.0
    label: str = "transformations"
    skipped_budget: bool = False


@dataclass
class GlossStats:
    stages: dict = field(default_factory=dict)
    budget_seconds: float = 20.0
    budget_expired: bool = False

    def record(self, stage, *, enabled=True, changes=0, saved_mm=0.0,
               elapsed_ms=0.0, label="transformations", skipped_budget=False):
        row = StageStats(enabled=enabled, changes=int(changes),
                         saved_mm=round(float(saved_mm), 4),
                         elapsed_ms=round(float(elapsed_ms), 3), label=label,
                         skipped_budget=skipped_budget)
        self.stages[stage] = row
        if not enabled:
            print(f"Track Gloss {stage}: désactivé")
        elif skipped_budget:
            print(f"Track Gloss {stage}: budget expiré")
        else:
            print(f"Track Gloss {stage}: {row.changes} {row.label}, "
                  f"-{row.saved_mm:.4f} mm, {row.elapsed_ms:.1f} ms")
        return row

    def as_dict(self):
        return {
            "budget_seconds": self.budget_seconds,
            "budget_expired": self.budget_expired,
            "stages": {stage: asdict(row)
                       for stage, row in self.stages.items()},
        }
