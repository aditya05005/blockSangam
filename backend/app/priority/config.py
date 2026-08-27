from dataclasses import dataclass


@dataclass(frozen=True)
class PriorityConfig:
    criticality_weight: float = 0.25
    defect_severity_weight: float = 0.25
    asset_criticality_weight: float = 0.20
    failure_consequence_weight: float = 0.20
    deferral_history_weight: float = 0.10
    mandatory_bonus: float = 0.10
    deferral_cap: int = 5

    def __post_init__(self) -> None:
        weights = (
            self.criticality_weight,
            self.defect_severity_weight,
            self.asset_criticality_weight,
            self.failure_consequence_weight,
            self.deferral_history_weight,
        )
        if any(weight < 0 for weight in weights):
            raise ValueError("Priority weights cannot be negative")
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("Priority weights must sum to 1.0")
        if not 0 <= self.mandatory_bonus <= 1:
            raise ValueError("mandatory_bonus must be between 0 and 1")
        if self.deferral_cap <= 0:
            raise ValueError("deferral_cap must be positive")

    def band(self, score: float) -> str:
        if score >= 0.85:
            return "CRITICAL"
        if score >= 0.66:
            return "HIGH"
        if score >= 0.33:
            return "MEDIUM"
        return "LOW"
