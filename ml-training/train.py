"""Train the authoritative maintenance outcome-risk priority model."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "backend" / "app" / "ml" / "models"
DATA = Path(__file__).resolve().parent / "data"
FEATURES = ["criticality", "defect_severity", "asset_criticality", "failure_consequence", "deferral_history", "mandatory", "duration_minutes", "restoration_minutes", "power_isolation", "snt_disconnection", "department_risk", "window_hours", "traffic_block"]


def build_training_data(rows: int = 8000, seed: int = 20260829) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "criticality": rng.integers(1, 6, rows), "defect_severity": rng.integers(1, 6, rows),
        "asset_criticality": rng.integers(1, 6, rows), "failure_consequence": rng.integers(1, 6, rows),
        "deferral_history": rng.integers(0, 9, rows), "mandatory": rng.binomial(1, .58, rows),
        "duration_minutes": rng.choice([30, 45, 60, 75, 90, 120, 150, 180], rows),
        "restoration_minutes": rng.choice([0, 10, 15, 20, 30, 45, 60], rows),
        "power_isolation": rng.binomial(1, .28, rows), "snt_disconnection": rng.binomial(1, .32, rows),
        "department_risk": rng.choice([.72, .82, .86], rows),
        "window_hours": rng.choice([1.5, 2, 3, 4, 8, 12, 24, 48, 72, 96], rows),
        "traffic_block": rng.binomial(1, .82, rows),
    })
    urgency = 1 - np.clip(frame.window_hours / 96, 0, 1)
    hazard = (-3.0 + .43*frame.defect_severity + .30*frame.failure_consequence + .22*frame.asset_criticality + .14*frame.deferral_history + .45*urgency + .22*frame.department_risk)
    failure_probability = 1 / (1 + np.exp(-hazard))
    safety_probability = np.clip(.03 + .08*(frame.failure_consequence-1) + .06*(frame.criticality-1) + .08*frame.power_isolation + .07*frame.snt_disconnection, .01, .82)
    emergency_probability = np.clip(.02 + .55*failure_probability + .06*frame.traffic_block, .01, .78)
    frame["failure_after_deferral"] = rng.binomial(1, failure_probability)
    frame["safety_escalation"] = rng.binomial(1, safety_probability)
    frame["emergency_intervention"] = rng.binomial(1, emergency_probability)
    frame["disruption_minutes"] = np.clip(rng.gamma(1.5 + 2.2*failure_probability, 24), 0, 240)
    effectiveness_mean = np.clip(.90 - .30*failure_probability - .04*frame.deferral_history/8, .35, .95)
    frame["maintenance_effectiveness"] = np.clip(rng.normal(effectiveness_mean, .09), 0, 1)
    frame["outcome_risk_score"] = np.clip(
        .34*frame.failure_after_deferral + .24*frame.safety_escalation +
        .19*frame.emergency_intervention + .16*(frame.disruption_minutes/240) +
        .07*(1-frame.maintenance_effectiveness), 0, 1,
    )
    return frame


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True); OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = build_training_data(); frame.to_csv(DATA / "priority_training_data.csv", index=False)
    train, test = train_test_split(frame, test_size=.2, random_state=42)
    model = RandomForestRegressor(n_estimators=72, min_samples_leaf=3, max_depth=10, random_state=42, n_jobs=-1)
    target = "outcome_risk_score"
    model.fit(train[FEATURES].to_numpy(), train[target])
    prediction = model.predict(test[FEATURES].to_numpy())
    absolute_error = np.abs(test[target].to_numpy() - prediction)
    bins = np.minimum((prediction * 10).astype(int), 9)
    q90_by_bin = [float(np.quantile(absolute_error[bins == index], .9)) if np.any(bins == index) else float(np.quantile(absolute_error, .9)) for index in range(10)]
    calibration = {"q90_absolute_error_by_bin": q90_by_bin, "feature_means": train[FEATURES].mean().tolist(), "feature_stds": train[FEATURES].std().tolist()}
    report = {"model": "RandomForestRegressor", "version": "outcome-risk-rf-3.0.0", "target": target, "target_definition": "Composite of failure after deferral, safety escalation, emergency intervention, disruption minutes, and maintenance effectiveness", "uses_existing_priority": False, "training_rows": len(train), "test_rows": len(test), "mae": round(float(mean_absolute_error(test[target], prediction)), 6), "r2": round(float(r2_score(test[target], prediction)), 6), "confidence_calibration": "held-out q90 error + ensemble disagreement + feature novelty", "features": FEATURES}
    joblib.dump({"model": model, "version": report["version"], "features": FEATURES, "metrics": report, "calibration": calibration}, OUTPUT / "priority_model.joblib")
    (OUTPUT / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
