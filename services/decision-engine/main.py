"""
MuleShield AI - Decision Engine Service
ZONE 4: RBI Rule Evaluation + ML Fusion
All 7 RBI Rules (R001-R007) + 5 Auto-Block Rules
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Shared core imports
from shared.core.security.auth import require_read, require_investigator
from shared.core.middleware.audit import AuditMiddleware
from shared.core.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("decision_engine")

app = FastAPI(
    title="MuleShield AI - Decision Engine",
    description="RBI Rule Evaluation + ML Fusion Decision Engine",
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


class DecisionRequest(BaseModel):
    features: Dict[str, float]
    ml_score: float
    account_id: str


class RuleHit(BaseModel):
    rule_id: str
    rule_name: str
    triggered: bool
    severity: str
    score_contribution: float


class DecisionResponse(BaseModel):
    final_score: float
    risk_level: str
    decision: str  # ALLOW, REVIEW, BLOCK
    rule_hits: List[RuleHit]
    auto_block_triggered: bool
    auto_block_reason: Optional[str]
    confidence: float


# RBI Rule Thresholds Configuration
RULE_THRESHOLDS = {
    "R001_HIGH_VELOCITY": 30,          # >30 txns/24h
    "R002_MANY_COUNTERPARTIES": 20,     # >20 unique counterparties
    "R003_EXTREME_CREDIT_FLOW": 8.0,    # ratio >8:1
    "R004_NEW_ACCOUNT_VELOCITY": 15,    # New + >15 txns
    "R005_NIGHT_TRANSACTIONS": 0.7,     # >70% at night
    "R006_LAYERING_ROUNDING": 0.3,      # >30% rounded amounts
    "R007_STRUCTURING": 49000,          # Amounts just below reporting
}

# Auto-block rules (hard blocks)
AUTO_BLOCK_RULES = [
    "HIGH_VELOCITY_30+",
    "MANY_COUNTERPARTIES_20+",
    "EXTREME_CREDIT_FLOW",
    "NEW_ACCOUNT_UNUSUAL_ACTIVITY",
    "ML_SCORE_HIGH_CONFIDENCE",
]


def evaluate_r001_high_velocity(features: Dict) -> RuleHit:
    """R001: High Transaction Velocity - >30 txns/24h"""
    triggered = features.get("txn_count_24h", 0) > RULE_THRESHOLDS["R001_HIGH_VELOCITY"]
    return RuleHit(
        rule_id="R001",
        rule_name="HIGH_VELOCITY",
        triggered=triggered,
        severity="HIGH" if triggered else "NONE",
        score_contribution=0.15 if triggered else 0.0,
    )


def evaluate_r002_many_counterparties(features: Dict) -> RuleHit:
    """R002: Many Unique Counterparties - >20 unique"""
    triggered = features.get("unique_counterparties", 0) > RULE_THRESHOLDS["R002_MANY_COUNTERPARTIES"]
    return RuleHit(
        rule_id="R002",
        rule_name="MANY_COUNTERPARTIES",
        triggered=triggered,
        severity="HIGH" if triggered else "NONE",
        score_contribution=0.15 if triggered else 0.0,
    )


def evaluate_r003_extreme_credit_flow(features: Dict) -> RuleHit:
    """R003: Extreme Credit Flow - ratio >8:1 (CRITICAL MULE PATTERN)"""
    triggered = features.get("credit_debit_ratio", 0) > RULE_THRESHOLDS["R003_EXTREME_CREDIT_FLOW"]
    return RuleHit(
        rule_id="R003",
        rule_name="EXTREME_CREDIT_FLOW",
        triggered=triggered,
        severity="CRITICAL" if triggered else "NONE",
        score_contribution=0.25 if triggered else 0.0,  # Highest weight
    )


def evaluate_r004_new_account_activity(features: Dict) -> RuleHit:
    """R004: New Account with Unusual Activity"""
    is_new = features.get("new_account_flag", 0) > 0.5
    high_velocity = features.get("txn_count_24h", 0) > RULE_THRESHOLDS["R004_NEW_ACCOUNT_VELOCITY"]
    triggered = is_new and high_velocity
    return RuleHit(
        rule_id="R004",
        rule_name="NEW_ACCOUNT_ACTIVITY",
        triggered=triggered,
        severity="HIGH" if triggered else "NONE",
        score_contribution=0.15 if triggered else 0.0,
    )


def evaluate_r005_night_transactions(features: Dict) -> RuleHit:
    """R005: Night Transactions Dominance - >70% at night"""
    triggered = features.get("night_transaction_ratio", 0) > RULE_THRESHOLDS["R005_NIGHT_TRANSACTIONS"]
    return RuleHit(
        rule_id="R005",
        rule_name="NIGHT_TRANSACTIONS",
        triggered=triggered,
        severity="MEDIUM" if triggered else "NONE",
        score_contribution=0.10 if triggered else 0.0,
    )


def evaluate_r006_layering_pattern(features: Dict) -> RuleHit:
    """R006: Layering Pattern Detection - Rounding behavior"""
    # Use std_amount as proxy for rounding consistency
    triggered = features.get("std_amount", 0) < 5000 and features.get("txn_count_24h", 0) > 10
    return RuleHit(
        rule_id="R006",
        rule_name="LAYERING_PATTERN",
        triggered=triggered,
        severity="MEDIUM" if triggered else "NONE",
        score_contribution=0.10 if triggered else 0.0,
    )


def evaluate_r007_structuring(features: Dict) -> RuleHit:
    """R007: Structuring Detection - Amounts below reporting threshold"""
    high_value_ratio = features.get("high_value_ratio", 0)
    many_txns = features.get("txn_count_24h", 0) > 20
    triggered = high_value_ratio < 0.1 and many_txns  # Many small txns, few large
    return RuleHit(
        rule_id="R007",
        rule_name="STRUCTURING",
        triggered=triggered,
        severity="MEDIUM" if triggered else "NONE",
        score_contribution=0.10 if triggered else 0.0,
    )


def check_auto_block(rule_hits: List[RuleHit], ml_score: float) -> tuple[bool, Optional[str]]:
    """Check if auto-block should be triggered"""
    # ML score high confidence
    if ml_score >= 0.7:
        return True, "ML_SCORE_HIGH_CONFIDENCE"
    
    # Critical rule hits
    for rule in rule_hits:
        if rule.rule_id == "R003" and rule.triggered:
            return True, "EXTREME_CREDIT_FLOW"
        if rule.rule_id == "R001" and rule.triggered:
            return True, "HIGH_VELOCITY_30+"
        if rule.rule_id == "R002" and rule.triggered:
            return True, "MANY_COUNTERPARTIES_20+"
        if rule.rule_id == "R004" and rule.triggered:
            return True, "NEW_ACCOUNT_UNUSUAL_ACTIVITY"
    
    return False, None


@app.on_event("startup")
async def startup():
    logger.info("decision_engine_started", rules=7, auto_block=5)


@app.post("/decide", response_model=DecisionResponse)
async def make_decision(
    request: DecisionRequest,
    user: dict = Depends(require_read),
):
    """
    Evaluate ALL 7 RBI Rules + ML Fusion
    Returns final decision with rule hits and auto-block status
    """
    try:
        # Evaluate all 7 RBI rules
        rule_hits = [
            evaluate_r001_high_velocity(request.features),
            evaluate_r002_many_counterparties(request.features),
            evaluate_r003_extreme_credit_flow(request.features),
            evaluate_r004_new_account_activity(request.features),
            evaluate_r005_night_transactions(request.features),
            evaluate_r006_layering_pattern(request.features),
            evaluate_r007_structuring(request.features),
        ]
        
        # Calculate rule-based score (sum of contributions)
        rule_score = sum(r.score_contribution for r in rule_hits)
        
        # Weighted fusion: ML 60%, Rules 40%
        final_score = (request.ml_score * 0.6) + (rule_score * 0.4)
        
        # Check auto-block
        auto_block, block_reason = check_auto_block(rule_hits, request.ml_score)
        
        # Determine decision
        if auto_block:
            decision = "BLOCK"
            risk_level = "CRITICAL"
        elif final_score >= 0.6:
            decision = "REVIEW"
            risk_level = "HIGH"
        elif final_score >= 0.3:
            decision = "REVIEW"
            risk_level = "MEDIUM"
        else:
            decision = "ALLOW"
            risk_level = "LOW"
        
        confidence = abs(final_score - 0.5) * 2
        
        logger.info(
            "decision_made",
            account_id=request.account_id,
            final_score=round(final_score, 3),
            decision=decision,
            auto_block=auto_block,
        )
        
        return DecisionResponse(
            final_score=float(final_score),
            risk_level=risk_level,
            decision=decision,
            rule_hits=rule_hits,
            auto_block_triggered=auto_block,
            auto_block_reason=block_reason,
            confidence=float(confidence),
        )
        
    except Exception as e:
        logger.error("decision_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rules")
async def get_rules(user: dict = Depends(require_read)):
    """Get all RBI rules with thresholds"""
    return {
        "rbi_rules": 7,
        "auto_block_rules": 5,
        "thresholds": RULE_THRESHOLDS,
        "auto_block": AUTO_BLOCK_RULES,
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "decision-engine", "rules": 7}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
