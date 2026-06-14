"""
MuleShield AI - Case Management Service
ZONE 5: Case Workflow + FIU-IND STR Generation
PostgreSQL persistence, investigator assignment, PDF generation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import uuid
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# Shared core imports
from shared.core.security.auth import require_investigator, require_read, require_auditor
from shared.core.database.session import get_db, init_db
from shared.core.database.models import Case, CaseStatus, RiskLevel, STRReport, Alert
from shared.core.middleware.audit import AuditMiddleware
from shared.core.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("case_management")

app = FastAPI(
    title="MuleShield AI - Case Management",
    description="Case Workflow + FIU-IND STR Generation",
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


class CreateCaseRequest(BaseModel):
    account_id: str
    transaction_ids: List[str]
    ml_score: float
    rule_hits: List[Dict]
    final_score: float
    risk_level: RiskLevel
    shap_explanation: Optional[Dict] = None


class AssignCaseRequest(BaseModel):
    case_id: str
    assigned_to: str
    notes: Optional[str] = None


class UpdateCaseStatusRequest(BaseModel):
    case_id: str
    status: CaseStatus
    notes: Optional[str] = None


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("case_management_started")


def generate_case_id() -> str:
    """Generate case ID in format: CASE-YYYYMMDD-XXXXXX"""
    date_str = datetime.utcnow().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"CASE-{date_str}-{suffix}"


def generate_str_number() -> str:
    """Generate STR report number for FIU-IND"""
    date_str = datetime.utcnow().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:8].upper()
    return f"STR-BOI-{date_str}-{suffix}"


def generate_str_pdf(str_number: str, case_data: Dict) -> str:
    """Generate FIU-IND compliant STR PDF report"""
    filename = f"/tmp/{str_number}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    story.append(Paragraph("SUSPICIOUS TRANSACTION REPORT (STR)", styles["Title"]))
    story.append(Paragraph("FIU-IND - Financial Intelligence Unit - India", styles["Heading2"]))
    story.append(Spacer(1, 20))
    
    # Header info
    header_data = [
        ["STR Number:", str_number],
        ["Reporting Entity:", "Bank of India"],
        ["Date Generated:", datetime.utcnow().isoformat()],
        ["Case ID:", case_data.get("case_id", "")],
    ]
    header_table = Table(header_data, colWidths=[150, 350])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 20))
    
    # Risk Assessment
    story.append(Paragraph("Risk Assessment", styles["Heading2"]))
    risk_data = [
        ["ML Score:", f"{case_data.get('ml_score', 0):.4f}"],
        ["Final Score:", f"{case_data.get('final_score', 0):.4f}"],
        ["Risk Level:", case_data.get("risk_level", "UNKNOWN")],
        ["Rules Triggered:", str(len(case_data.get("rule_hits", [])))],
    ]
    risk_table = Table(risk_data, colWidths=[150, 350])
    risk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(risk_table)
    
    doc.build(story)
    return filename


@app.post("/cases", status_code=201)
async def create_case(
    request: CreateCaseRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_investigator),
):
    """Create new investigation case"""
    case_id = generate_case_id()
    
    case = Case(
        id=uuid.uuid4(),
        case_id=case_id,
        account_id=request.account_id,
        transaction_ids=request.transaction_ids,
        ml_score=request.ml_score,
        rule_hits=request.rule_hits,
        final_score=request.final_score,
        risk_level=request.risk_level,
        status=CaseStatus.OPEN,
        shap_explanation=request.shap_explanation,
    )
    
    db.add(case)
    
    # Create alert if high risk
    if request.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
        alert = Alert(
            id=uuid.uuid4(),
            alert_type="NEW_CASE",
            severity="CRITICAL" if request.risk_level == RiskLevel.CRITICAL else "HIGH",
            message=f"New {request.risk_level.value} risk case created for account {request.account_id}",
            account_id=request.account_id,
            case_id=case.id,
        )
        db.add(alert)
    
    await db.commit()
    
    logger.info("case_created", case_id=case_id, risk_level=request.risk_level.value)
    return {"case_id": case_id, "status": "created"}


@app.get("/cases")
async def list_cases(
    status: Optional[CaseStatus] = Query(None),
    risk_level: Optional[RiskLevel] = Query(None),
    assigned_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_read),
):
    """List and filter cases"""
    query = select(Case)
    
    filters = []
    if status:
        filters.append(Case.status == status)
    if risk_level:
        filters.append(Case.risk_level == risk_level)
    if assigned_to:
        filters.append(Case.assigned_to == assigned_to)
    
    if filters:
        query = query.where(and_(*filters))
    
    result = await db.execute(query.order_by(Case.created_at.desc()))
    cases = result.scalars().all()
    
    return {
        "total": len(cases),
        "cases": [
            {
                "case_id": c.case_id,
                "account_id": c.account_id,
                "risk_level": c.risk_level.value,
                "status": c.status.value,
                "assigned_to": c.assigned_to,
                "final_score": float(c.final_score) if c.final_score else 0,
                "created_at": c.created_at.isoformat(),
            }
            for c in cases
        ],
    }


@app.post("/cases/assign")
async def assign_case(
    request: AssignCaseRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_investigator),
):
    """Assign case to investigator"""
    result = await db.execute(select(Case).where(Case.case_id == request.case_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    case.assigned_to = request.assigned_to
    case.status = CaseStatus.UNDER_INVESTIGATION
    if request.notes:
        case.notes = (case.notes or "") + f"\n[{datetime.utcnow().isoformat()}] {request.notes}"
    
    await db.commit()
    return {"status": "assigned", "case_id": request.case_id}


@app.post("/cases/status")
async def update_case_status(
    request: UpdateCaseStatusRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_investigator),
):
    """Update case status"""
    result = await db.execute(select(Case).where(Case.case_id == request.case_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    case.status = request.status
    case.updated_at = datetime.utcnow()
    if request.notes:
        case.notes = (case.notes or "") + f"\n[{datetime.utcnow().isoformat()}] {request.notes}"
    
    await db.commit()
    return {"status": "updated", "case_id": request.case_id}


@app.post("/cases/{case_id}/generate-str")
async def generate_str_report(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auditor),
):
    """Generate FIU-IND compliant STR report"""
    result = await db.execute(select(Case).where(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    str_number = generate_str_number()
    
    # Generate PDF
    case_data = {
        "case_id": case.case_id,
        "ml_score": float(case.ml_score) if case.ml_score else 0,
        "final_score": float(case.final_score) if case.final_score else 0,
        "risk_level": case.risk_level.value,
        "rule_hits": case.rule_hits or [],
    }
    pdf_path = generate_str_pdf(str_number, case_data)
    
    # Save STR record
    str_report = STRReport(
        id=uuid.uuid4(),
        str_number=str_number,
        case_id=case.id,
        fiu_format=case_data,
        pdf_path=pdf_path,
        generated_by=user["username"],
    )
    db.add(str_report)
    
    case.str_generated = True
    await db.commit()
    
    logger.info("str_generated", str_number=str_number, case_id=case_id)
    return {"str_number": str_number, "pdf_path": pdf_path, "status": "generated"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "case-management"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
