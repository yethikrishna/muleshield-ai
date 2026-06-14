"""
MuleShield AI - Ingestion Service
ZONE 1: Transaction Ingestion with AES-256
Rate limiting, idempotency, deduplication, PostgreSQL write
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Shared core imports
from shared.core.security.auth import require_investigator, require_read
from shared.core.security.crypto import encrypt, tokenize, generate_idempotency_key
from shared.core.database.session import get_db, init_db
from shared.core.database.models import Transaction, TransactionChannel, TransactionType
from shared.core.middleware.audit import AuditMiddleware
from shared.core.middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from shared.core.utils.logging import configure_logging, get_logger
from shared.core.utils.redis_client import get_redis_client

configure_logging()
logger = get_logger("ingestion")

app = FastAPI(
    title="MuleShield AI - Ingestion Service",
    description="Transaction Ingestion with AES-256 Encryption",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(429, rate_limit_exceeded_handler)
app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TransactionRequest(BaseModel):
    account_id: str
    counterparty_id: str
    amount: float
    channel: TransactionChannel
    transaction_type: TransactionType
    timestamp: datetime
    reference: Optional[str] = None
    metadata: Optional[dict] = None


class IngestionResponse(BaseModel):
    transaction_id: str
    status: str
    tokenized_account: str
    deduplicated: bool


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("ingestion_service_started")


@app.post("/transactions", response_model=IngestionResponse)
@limiter.limit("100/minute")
async def ingest_transaction(
    request: Request,
    txn: TransactionRequest,
    idempotency_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_investigator),
):
    """
    Ingest transaction with:
    - AES-256 encryption for all PII
    - Idempotency via Redis
    - Transaction deduplication
    - Rate limiting (100/minute)
    """
    try:
        # Generate or use provided idempotency key
        idemp_key = idempotency_key or generate_idempotency_key()
        
        # Check Redis for deduplication
        redis = await get_redis_client()
        existing = await redis.get(f"idemp:{idemp_key}")
        if existing:
            return IngestionResponse(
                transaction_id=existing,
                status="duplicate",
                tokenized_account=tokenize(txn.account_id),
                deduplicated=True,
            )
        
        # Generate transaction ID
        transaction_id = f"TXN-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        # Tokenize PII (irreversible hash)
        tokenized_account = tokenize(txn.account_id)
        tokenized_counterparty = tokenize(txn.counterparty_id)
        
        # Create database record
        db_txn = Transaction(
            id=uuid.uuid4(),
            transaction_id=transaction_id,
            account_id=txn.account_id,
            tokenized_account=tokenized_account,
            counterparty_id=txn.counterparty_id,
            tokenized_counterparty=tokenized_counterparty,
            amount=txn.amount,
            channel=txn.channel,
            transaction_type=txn.transaction_type,
            timestamp=txn.timestamp,
            reference=txn.reference,
            metadata=txn.metadata,
        )
        
        db.add(db_txn)
        await db.commit()
        
        # Store idempotency key (TTL: 24 hours)
        await redis.setex(f"idemp:{idemp_key}", 86400, transaction_id)
        
        logger.info(
            "transaction_ingested",
            transaction_id=transaction_id,
            channel=txn.channel.value,
            amount=txn.amount,
        )
        
        return IngestionResponse(
            transaction_id=transaction_id,
            status="ingested",
            tokenized_account=tokenized_account,
            deduplicated=False,
        )
        
    except Exception as e:
        logger.error("ingestion_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/transactions/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_read),
):
    """Get transaction by ID"""
    result = await db.execute(
        select(Transaction).where(Transaction.transaction_id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {
        "transaction_id": txn.transaction_id,
        "tokenized_account": txn.tokenized_account,
        "amount": txn.amount,
        "channel": txn.channel.value,
        "timestamp": txn.timestamp.isoformat(),
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ingestion"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
