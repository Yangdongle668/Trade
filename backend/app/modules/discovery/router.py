import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import CurrentUser, get_current_user, get_tenant_db
from app.modules.audit import service as audit
from app.modules.contact.models import Contact, EmailCandidate
from app.modules.discovery.models import Company, Lead, ResearchFact

router = APIRouter(prefix="/api/leads", tags=["leads"])


class FactOut(BaseModel):
    text: str
    source_url: str


class CandidateOut(BaseModel):
    email: str
    confidence: str
    verify_status: str


class ContactOut(BaseModel):
    id: str
    full_name: str
    role_title: str
    emails: list[CandidateOut]


class LeadDetailOut(BaseModel):
    id: str
    status: str
    score: int
    score_reason: str
    company_name: str
    domain: str
    country: str
    city: str
    source: str
    facts: list[FactOut]
    contacts: list[ContactOut]


def _get_lead(db: Session, current: CurrentUser, lead_id: uuid.UUID) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.tenant_id != current.tenant_id:
        raise HTTPException(404, "线索不存在")
    return lead


@router.get("/{lead_id}", response_model=LeadDetailOut)
def lead_detail(lead_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_tenant_db)) -> LeadDetailOut:
    lead = _get_lead(db, current, lead_id)
    company = db.get(Company, lead.company_id)
    facts = db.execute(
        select(ResearchFact).where(ResearchFact.domain == company.domain)
        .order_by(ResearchFact.created_at)
    ).scalars().all()
    contacts = db.execute(
        select(Contact).where(Contact.tenant_id == current.tenant_id,
                              Contact.company_id == company.id)
    ).scalars().all()
    contact_outs = []
    for c in contacts:
        emails = db.execute(
            select(EmailCandidate).where(EmailCandidate.contact_id == c.id)
        ).scalars().all()
        contact_outs.append(ContactOut(
            id=str(c.id), full_name=c.full_name, role_title=c.role_title,
            emails=[CandidateOut(email=e.email, confidence=e.confidence,
                                 verify_status=e.verify_status) for e in emails],
        ))
    return LeadDetailOut(
        id=str(lead.id), status=lead.status, score=lead.score, score_reason=lead.score_reason,
        company_name=company.name, domain=company.domain, country=company.country,
        city=company.city, source=company.source,
        facts=[FactOut(text=f.fact_text, source_url=f.source_url) for f in facts],
        contacts=contact_outs,
    )


@router.post("/{lead_id}/exclude", status_code=204)
def exclude_lead(lead_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_tenant_db)) -> None:
    """人工排除（线索池「排除」操作，反馈用于校准打分 FR-LEAD-05）。"""
    lead = _get_lead(db, current, lead_id)
    if lead.status in ("in_sequence", "replied", "hot"):
        raise HTTPException(409, f"状态 {lead.status} 的线索不能排除")
    lead.status = "excluded"
    audit.record(db, current.tenant_id, "lead", lead.id, "lead.excluded_manual", {})
    db.commit()
