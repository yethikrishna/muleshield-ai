"""
MuleShield AI - Feature Store Service
ZONE 2: 18 Behavioral Features Calculation
Redis caching, time-window aggregation, PostgreSQL persistence
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

# Shared core imports
from shared.core.security.auth import require_read
from shared.core.database.session import get_db, init_db
from shared.core.database.models import Transaction, AccountFeature, TransactionType
from shared.core.middleware.audit import AuditMiddleware
from shared.core.utils.logging import configure_logging, get_logger
from shared.core.utils.redis_client import get_redis_client

configure_logging()
logger = get_logger("feature_store")

app = FastAPI(
    title="MuleShield AI - Feature Store",
    description="18 Behavioral Features Calculation",
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


class FeatureResponse(BaseModel):
    account_id: str
    features: Dict[str, float]
    cached: bool
    version: int


FEATURE_LIST = [
    "txn_count_1h", "txn_count_24h", "txn_count_7d",
    "credit_count", "debit_count", "credit_debit_ratio",
    "total_amount", "avg_amount", "std_amount",
    "unique_counterparties", "unique_channels",
    "velocity_score", "amount_velocity",
    "night_transaction_ratio", "weekend_ratio",
    "new_account_flag", "high_value_ratio",
    "counterparty_diversity",
]


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("feature_store_started")


async def calculate_features(account_id: str, db: AsyncSession) -> Dict[str, float]:
    """Calculate ALL 18 features dynamically from transaction history"""
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(hours=24)
    seven_days_ago = now - timedelta(days=7)
    
    # Get all transactions for this account
    result = await db.execute(
        select(Transaction).where(Transaction.account_id == account_id)
    )
    txns = result.scalars().all()
    
    if not txns:
        return {f: 0.0 for f in FEATURE_LIST}
    
    # Time window counts
    txns_1h = [t for t in txns if t.timestamp >= one_hour_ago]
    txns_24h = [t for t in txns if t.timestamp >= one_day_ago]
    txns_7d = [t for t in txns if t.timestamp >= seven_days_ago]
    
    # Credit/debit breakdown
    credits = [t for t in txns_7d if t.transaction_type == TransactionType.CREDIT]
    debits = [t for t in txns_7d if t.transaction_type == TransactionType.DEBIT]
    
    # Amount statistics
    amounts = [t.amount for t in txns_7d]
    total_amount = sum(amounts)
    avg_amount = np.mean(amounts) if amounts else 0
    std_amount = np.std(amounts) if len(amounts) > 1 else 0
    
    # Diversity metrics
    unique_cps = len(set(t.counterparty_id for t in txns_7d))
    unique_chs = len(set(t.channel.value for t in txns_7d))
    
    # Velocity scores (normalized)
    velocity_score = min(1.0, len(txns_24h) / 50)
    amount_velocity = min(1.0, total_amount / 1000000)
    
    # Temporal patterns
    night_txns = [t for t in txns_7d if 0 <= t.timestamp.hour < 6]
    weekend_txns = [t for t in txns_7d if t.timestamp.weekday() >= 5]
    night_ratio = len(night_txns) / len(txns_7d) if txns_7d else 0
    weekend_ratio = len(weekend_txns) / len(txns_7d) if txns_7d else 0
    
    # High value ratio (>= 50000)
    high_value = [t for t in txns_7d if t.amount >= 50000]
    high_value_ratio = len(high_value) / len(txns_7d) if txns_7d else 0
    
    # Counterparty diversity (normalized)
    cp_diversity = min(1.0, unique_cps / 30)
    
    # New account flag (first txn within 30 days)
    first_txn = min(t.timestamp for t in txns)
    new_account_flag = 1.0 if (now - first_txn).days < 30 else 0.0
    
    # Credit/debit ratio (handle division by zero)
    cd_ratio = len(credits) / max(1, len(debits))
    
    return {
        "txn_count_1h": float(len(txns_1h)),
        "txn_count_24h": float(len(txns_24h)),
        "txn_count_7d": float(len(txns_7d)),
        "credit_count": float(len(credits)),
        "debit_count": float(len(debits)),
        "credit_debit_ratio": float(cd_ratio),
        "total_amount": float(total_amount),
        "avg_amount": float(avg_amount),
        "std_amount": float(std_amount),
        "unique_counterparties": float(unique_cps),
        "unique_channels": float(unique_chs),
        "velocity_score": float(velocity_score),
        "amount_velocity": float(amount_velocity),
        "night_transaction_ratio": float(night_ratio),
        "weekend_ratio": float(weekend_ratio),
        "new_account_flag": float(new_account_flag),
        "high_value_ratio": float(high_value_ratio),
        "counterparty_diversity": float(cp_diversity),
    }


@app.get("/features/{account_id}", response_model=FeatureResponse)
async def get_features(
    account_id: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_read),
):
    """
    Get 18 behavioral features for an account:
    - Redis cached (TTL: 5 minutes)
    - Dynamic calculation from transaction history
    - PostgreSQL persistence
    """
    redis = await get_redis_client()
    
    # Check cache first
    cache_key = f"features:{account_id}"
    if not refresh:
        cached = await redis.get(cache_key)
        if cached:
            import json
            return FeatureResponse(
                account_id=account_id,
                features=json.loads(cached),
                cached=True,
                version=1,
            )
    
    # Calculate features
    features = await calculate_features(account_id, db)
    
    # Cache result (5 minutes)
    import json
    await redis.setex(cache_key, 300, json.dumps(features))
    
    # Persist to database
    feature_record = AccountFeature(
        account_id=account_id,
        **features,
    )
    db.add(feature_record)
    await db.commit()
    
    logger.info("features_calculated", account_id=account_id)
    
    return FeatureResponse(
        account_id=account_id,
        features=features,
        cached=False,
        version=1,
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "feature-store", "features": 18}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
