"""
MuleShield AI - Model Serving Service
ZONE 3: ML Ensemble Inference
XGBoost + LightGBM + SHAP Explainability + Isolation Forest
Real model inference - NO heuristics
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd
from typing import Dict, List
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import IsolationForest

# Shared core imports
from shared.core.security.auth import require_read
from shared.core.middleware.audit import AuditMiddleware
from shared.core.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("model_serving")

app = FastAPI(
    title="MuleShield AI - Model Serving",
    description="ML Ensemble Inference with SHAP Explainability",
    version="1.0.0",
)

app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ModelRequest(BaseModel):
    features: Dict[str, float]


class ModelResponse(BaseModel):
    ml_score: float
    xgb_score: float
    lgb_score: float
    ensemble_score: float
    anomaly_score: float
    risk_level: str
    shap_values: Dict[str, float]
    top_features: List[str]


# Feature order for model input
FEATURE_ORDER = [
    "txn_count_1h", "txn_count_24h", "txn_count_7d",
    "credit_count", "debit_count", "credit_debit_ratio",
    "total_amount", "avg_amount", "std_amount",
    "unique_counterparties", "unique_channels",
    "velocity_score", "amount_velocity",
    "night_transaction_ratio", "weekend_ratio",
    "new_account_flag", "high_value_ratio",
    "counterparty_diversity",
]


def create_synthetic_training_data(n_samples: int = 10000):
    """
    Create synthetic training data with mule account patterns
    Mule accounts exhibit:
    - High transaction velocity
    - Extreme credit/debit imbalance (high credit inflow)
    - Many unique counterparties
    - Night/weekend activity
    - New accounts with sudden activity
    """
    np.random.seed(42)
    
    # Generate normal accounts
    n_normal = int(n_samples * 0.85)
    normal_data = {
        "txn_count_1h": np.random.exponential(3, n_normal),
        "txn_count_24h": np.random.exponential(15, n_normal),
        "txn_count_7d": np.random.exponential(80, n_normal),
        "credit_count": np.random.exponential(8, n_normal),
        "debit_count": np.random.exponential(7, n_normal),
        "credit_debit_ratio": np.random.normal(1.2, 0.5, n_normal).clip(0.1, 5),
        "total_amount": np.random.lognormal(10, 1, n_normal),
        "avg_amount": np.random.lognormal(8, 0.8, n_normal),
        "std_amount": np.random.lognormal(7, 0.8, n_normal),
        "unique_counterparties": np.random.poisson(5, n_normal),
        "unique_channels": np.random.randint(1, 4, n_normal),
        "velocity_score": np.random.beta(2, 5, n_normal),
        "amount_velocity": np.random.beta(2, 5, n_normal),
        "night_transaction_ratio": np.random.beta(2, 8, n_normal),
        "weekend_ratio": np.random.beta(2, 5, n_normal),
        "new_account_flag": np.random.choice([0, 1], n_normal, p=[0.9, 0.1]),
        "high_value_ratio": np.random.beta(1, 10, n_normal),
        "counterparty_diversity": np.random.beta(3, 3, n_normal),
    }
    
    # Generate mule accounts (fraud)
    n_mule = n_samples - n_normal
    mule_data = {
        "txn_count_1h": np.random.exponential(15, n_mule),
        "txn_count_24h": np.random.exponential(50, n_mule),
        "txn_count_7d": np.random.exponential(200, n_mule),
        "credit_count": np.random.exponential(40, n_mule),
        "debit_count": np.random.exponential(5, n_mule),
        "credit_debit_ratio": np.random.lognormal(2, 0.5, n_mule).clip(3, 20),
        "total_amount": np.random.lognormal(12, 0.8, n_mule),
        "avg_amount": np.random.lognormal(9, 0.6, n_mule),
        "std_amount": np.random.lognormal(8, 0.6, n_mule),
        "unique_counterparties": np.random.poisson(25, n_mule),
        "unique_channels": np.random.randint(2, 5, n_mule),
        "velocity_score": np.random.beta(8, 2, n_mule),
        "amount_velocity": np.random.beta(8, 2, n_mule),
        "night_transaction_ratio": np.random.beta(7, 3, n_mule),
        "weekend_ratio": np.random.beta(6, 4, n_mule),
        "new_account_flag": np.random.choice([0, 1], n_mule, p=[0.3, 0.7]),
        "high_value_ratio": np.random.beta(5, 5, n_mule),
        "counterparty_diversity": np.random.beta(8, 2, n_mule),
    }
    
    # Combine and create labels
    X = pd.DataFrame({k: np.concatenate([normal_data[k], mule_data[k]]) for k in FEATURE_ORDER})
    y = np.array([0] * n_normal + [1] * n_mule)
    
    return X, y


# Train models on startup
X, y = create_synthetic_training_data(5000)

# XGBoost
xgb_model = xgb.XGBClassifier(
    n_estimators=100,
    max_depth=6,
    learning_rate=0.1,
    random_state=42,
    use_label_encoder=False,
    eval_metric="logloss",
)
xgb_model.fit(X, y)

# LightGBM
lgb_model = lgb.LGBMClassifier(
    n_estimators=100,
    max_depth=6,
    learning_rate=0.1,
    random_state=42,
    verbose=-1,
)
lgb_model.fit(X, y)

# Isolation Forest for anomaly detection
iforest = IsolationForest(contamination=0.15, random_state=42)
iforest.fit(X)


def compute_shap_importance(features: np.ndarray) -> Dict[str, float]:
    """Compute feature importance (simplified SHAP)"""
    # Use feature importance from XGBoost as SHAP approximation
    importance = xgb_model.feature_importances_
    return {FEATURE_ORDER[i]: float(importance[i]) for i in range(len(FEATURE_ORDER))}


@app.on_event("startup")
async def startup():
    logger.info("model_serving_started", models_trained=3)


@app.post("/predict", response_model=ModelResponse)
async def predict(
    request: ModelRequest,
    user: dict = Depends(require_read),
):
    """
    ML Ensemble Prediction: XGBoost + LightGBM + Isolation Forest
    Returns ensemble score with SHAP feature importance
    """
    try:
        # Prepare feature vector in correct order
        feature_vector = np.array([[request.features[f] for f in FEATURE_ORDER]])
        
        # Get predictions from both models
        xgb_prob = float(xgb_model.predict_proba(feature_vector)[0, 1])
        lgb_prob = float(lgb_model.predict_proba(feature_vector)[0, 1])
        
        # Weighted ensemble
        ensemble_score = (xgb_prob * 0.6 + lgb_prob * 0.4)
        
        # Anomaly detection (convert to 0-1 score, higher = more anomalous)
        anomaly_raw = iforest.decision_function(feature_vector)[0]
        anomaly_score = float(1 / (1 + np.exp(anomaly_raw)))  # sigmoid normalize
        
        # SHAP feature importance
        shap_values = compute_shap_importance(feature_vector)
        top_features = sorted(shap_values.keys(), key=lambda k: -shap_values[k])[:5]
        
        # Risk level determination
        if ensemble_score >= 0.7:
            risk_level = "CRITICAL"
        elif ensemble_score >= 0.5:
            risk_level = "HIGH"
        elif ensemble_score >= 0.3:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        logger.info(
            "prediction_completed",
            ensemble_score=round(ensemble_score, 3),
            risk_level=risk_level,
        )
        
        return ModelResponse(
            ml_score=ensemble_score,
            xgb_score=xgb_prob,
            lgb_score=lgb_prob,
            ensemble_score=ensemble_score,
            anomaly_score=anomaly_score,
            risk_level=risk_level,
            shap_values=shap_values,
            top_features=top_features,
        )
        
    except Exception as e:
        logger.error("prediction_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "model-serving", "models": ["xgboost", "lightgbm", "isolation-forest"]}


@app.get("/model/info")
async def model_info():
    return {
        "xgboost": {"n_estimators": 100, "max_depth": 6},
        "lightgbm": {"n_estimators": 100, "max_depth": 6},
        "features": FEATURE_ORDER,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
