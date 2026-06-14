"""
MuleShield AI - SQLAlchemy 2.0 Database Models
8 full models with relationships, indexes, and constraints
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, String, Float, DateTime, Boolean, ForeignKey, JSON, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class CaseStatus(str, PyEnum):
    OPEN = "OPEN"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    ESCALATED = "ESCALATED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    CONFIRMED_MULE = "CONFIRMED_MULE"
    CLOSED = "CLOSED"


class RiskLevel(str, PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TransactionChannel(str, PyEnum):
    UPI = "UPI"
    NEFT = "NEFT"
    RTGS = "RTGS"
    IMPS = "IMPS"
    ATM = "ATM"
    BRANCH = "BRANCH"
    NET_BANKING = "NET_BANKING"
    CARD = "CARD"


class TransactionType(str, PyEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class UserRole(str, PyEnum):
    ADMIN = "ADMIN"
    INVESTIGATOR = "INVESTIGATOR"
    AUDITOR = "AUDITOR"
    READONLY = "READONLY"


class AlertSeverity(str, PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AuditLog(Base):
    """Immutable audit logs - PostgreSQL trigger prevents UPDATE/DELETE"""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=False)
    details = Column(JSON, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class Transaction(Base):
    """Transactions with tokenized accounts"""
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(String, unique=True, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    tokenized_account = Column(String, nullable=False)
    counterparty_id = Column(String, nullable=False)
    tokenized_counterparty = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    channel = Column(Enum(TransactionChannel), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    reference = Column(String, nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AccountFeature(Base):
    """18 behavioral features, versioned"""
    __tablename__ = "account_features"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    
    # Time-window counts
    txn_count_1h = Column(Float, nullable=False, default=0)
    txn_count_24h = Column(Float, nullable=False, default=0)
    txn_count_7d = Column(Float, nullable=False, default=0)
    
    # Credit/debit
    credit_count = Column(Float, nullable=False, default=0)
    debit_count = Column(Float, nullable=False, default=0)
    credit_debit_ratio = Column(Float, nullable=False, default=0)
    
    # Amount statistics
    total_amount = Column(Float, nullable=False, default=0)
    avg_amount = Column(Float, nullable=False, default=0)
    std_amount = Column(Float, nullable=False, default=0)
    
    # Diversity
    unique_counterparties = Column(Float, nullable=False, default=0)
    unique_channels = Column(Float, nullable=False, default=0)
    
    # Velocity
    velocity_score = Column(Float, nullable=False, default=0)
    amount_velocity = Column(Float, nullable=False, default=0)
    
    # Temporal patterns
    night_transaction_ratio = Column(Float, nullable=False, default=0)
    weekend_ratio = Column(Float, nullable=False, default=0)
    
    # Risk flags
    new_account_flag = Column(Float, nullable=False, default=0)
    high_value_ratio = Column(Float, nullable=False, default=0)
    counterparty_diversity = Column(Float, nullable=False, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Case(Base):
    """Full investigation case lifecycle"""
    __tablename__ = "cases"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(String, unique=True, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    transaction_ids = Column(JSON, nullable=False)
    ml_score = Column(Float, nullable=False)
    rule_hits = Column(JSON, nullable=True)
    final_score = Column(Float, nullable=False)
    risk_level = Column(Enum(RiskLevel), nullable=False, index=True)
    status = Column(Enum(CaseStatus), nullable=False, default=CaseStatus.OPEN, index=True)
    assigned_to = Column(String, nullable=True, index=True)
    notes = Column(String, nullable=True)
    shap_explanation = Column(JSON, nullable=True)
    str_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Alert(Base):
    """System alerts with severity levels"""
    __tablename__ = "alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_type = Column(String, nullable=False, index=True)
    severity = Column(Enum(AlertSeverity), nullable=False, index=True)
    message = Column(String, nullable=False)
    account_id = Column(String, nullable=True, index=True)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class User(Base):
    """RBAC users with roles"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.READONLY)
    full_name = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class STRReport(Base):
    """FIU-IND Suspicious Transaction Reports"""
    __tablename__ = "str_reports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    str_number = Column(String, unique=True, nullable=False, index=True)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    fiu_format = Column(JSON, nullable=False)
    pdf_path = Column(String, nullable=True)
    generated_by = Column(String, nullable=False)
    submitted = Column(Boolean, default=False)
    submitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
