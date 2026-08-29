# BlockSangam ML priority training

Run `python ml-training/train.py` from the repository root to reproduce the model artifact. The generated labelled cases model maintenance risk interactions and are suitable for this prototype; production deployment should retrain on reviewed historical railway decisions and observed outcomes.

The model target is `outcome_risk_score`, derived from simulated post-deferral failure, safety escalation, emergency intervention, disruption, and maintenance effectiveness outcomes. This trained score is the sole operational priority supplied to CP-SAT.

The runtime backend requires `backend/app/ml/models/priority_model.joblib` and has no rules fallback. Mandatory status remains a scheduler hard constraint and is never delegated solely to ML.
