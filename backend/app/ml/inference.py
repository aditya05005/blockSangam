from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

from app.domain.models import Department, Task


FEATURE_NAMES = (
    "criticality", "defect_severity", "asset_criticality", "failure_consequence",
    "deferral_history", "mandatory", "duration_minutes", "restoration_minutes",
    "power_isolation", "snt_disconnection", "department_risk", "window_hours",
    "traffic_block",
)


@dataclass(frozen=True)
class MLPriorityPrediction:
    score: float
    confidence: float
    factors: tuple[str, ...]
    model_version: str


class MLPriorityPredictor:
    def __init__(self, artifact_path: str | Path | None = None):
        default = Path(__file__).resolve().parent / "models" / "priority_model.joblib"
        self.artifact_path = Path(artifact_path) if artifact_path else default
        self.bundle = joblib.load(self.artifact_path)
        self.bundle["model"].n_jobs = 1

    def predict(self, task: Task) -> MLPriorityPrediction:
        values = np.asarray([self._features(task)], dtype=float)
        model = self.bundle["model"]
        score = float(np.clip(model.predict(values)[0], 0.0, 1.0))
        tree_predictions = np.asarray([tree.predict(values)[0] for tree in model.estimators_[::3]])
        calibration = self.bundle.get("calibration", {})
        bin_index = min(int(score * 10), 9)
        held_out_error = float(calibration.get("q90_absolute_error_by_bin", [0.08] * 10)[bin_index])
        ensemble_uncertainty = float(tree_predictions.std())
        means = np.asarray(calibration.get("feature_means", [0.0] * len(FEATURE_NAMES)))
        stds = np.asarray(calibration.get("feature_stds", [1.0] * len(FEATURE_NAMES)))
        novelty = float(np.mean(np.maximum(np.abs((values[0] - means) / np.maximum(stds, 1e-6)) - 1.5, 0)))
        ambiguity = 1.0 - min(abs(score - 0.5) * 2.0, 1.0)
        uncertainty = max(held_out_error, ensemble_uncertainty * 1.35)
        confidence = float(np.clip(1.0 - 1.10 * uncertainty - 0.09 * ambiguity - 0.04 * novelty, 0.35, 0.88))
        importances = model.feature_importances_
        normalized = self._normalized(task)
        ranked = sorted(zip(FEATURE_NAMES, importances * normalized), key=lambda item: item[1], reverse=True)
        labels = {
            "criticality": "Criticality", "defect_severity": "Defect severity",
            "asset_criticality": "Asset criticality", "failure_consequence": "Failure consequence",
            "deferral_history": "Deferral history", "mandatory": "Mandatory safety status",
            "duration_minutes": "Work duration", "restoration_minutes": "Restoration time",
            "power_isolation": "Power isolation", "snt_disconnection": "S&T disconnection",
            "department_risk": "Department risk profile",
            "window_hours": "Planning-window urgency", "traffic_block": "Traffic-block exposure",
        }
        factors = tuple(labels[name] for name, contribution in ranked if contribution > 0)[:3]
        return MLPriorityPrediction(round(score, 6), round(confidence, 4), factors, self.bundle["version"])

    @staticmethod
    def _features(task: Task) -> list[float]:
        department_risk = {Department.ENGINEERING: 0.72, Department.SNT: 0.82, Department.TRD: 0.86}[task.department]
        window_hours = min((task.latest_finish - task.earliest_start).total_seconds() / 3600, 120)
        return [
            task.criticality, task.defect_severity, task.asset_criticality, task.failure_consequence,
            min(task.deferral_history, 8), int(task.mandatory), task.duration_minutes,
            task.restoration_minutes, int(task.requires_power_isolation),
            int(task.requires_snt_disconnection), department_risk, window_hours,
            int(task.requires_traffic_block),
        ]

    @staticmethod
    def _normalized(task: Task) -> np.ndarray:
        raw = MLPriorityPredictor._features(task)
        scales = np.asarray([5, 5, 5, 5, 8, 1, 180, 60, 1, 1, 1, 120, 1], dtype=float)
        return np.asarray(raw, dtype=float) / scales


@lru_cache(maxsize=1)
def load_priority_predictor() -> MLPriorityPredictor:
    return MLPriorityPredictor()
