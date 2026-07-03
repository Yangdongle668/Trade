"""审批流 API（今日待办的「待审批开发信」段，02 文档 P1）。"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import CurrentUser, get_current_user, get_tenant_db
from app.modules.audit import service as audit
from app.modules.contact.models import Contact
from app.modules.discovery.models import Company, Lead
from app.modules.sequence.models import SendJob, SequenceState
from app.modules.sequence.service import enroll_lead as _enroll
from app.modules.sequence.service import EnrollError

router = APIRouter(prefix="/api/sendjobs", tags=["sendjobs"])


class SendJobOut(BaseModel):
    id: str
    step_no: int
    status: str
    scheduled_at: str
    subject: str
    body_text: str
    company_name: str
    domain: str
    contact_name: str
    fact_urls: list[str]


@router.get("/pending", response_model=list[SendJobOut])
def pending(current: CurrentUser = Depends(get_current_user),
            db: Session = Depends(get_tenant_db)) -> list[SendJobOut]:
    rows = db.execute(
        select(SendJob, SequenceState, Lead, Company, Contact)
        .join(SequenceState, SendJob.sequence_state_id == SequenceState.id)
        .join(Lead, SequenceState.lead_id == Lead.id)
        .join(Company, Lead.company_id == Company.id)
        .join(Contact, SequenceState.contact_id == Contact.id)
        .where(SendJob.tenant_id == current.tenant_id,
               SendJob.status == "pending_approval")
        .order_by(SendJob.created_at)
    ).all()
    return [SendJobOut(
        id=str(j.id), step_no=j.step_no, status=j.status,
        scheduled_at=j.scheduled_at.isoformat(), subject=j.subject, body_text=j.body_text,
        company_name=co.name or co.domain, domain=co.domain, contact_name=c.full_name,
        fact_urls=j.generation_meta.get("fact_urls", []),
    ) for j, s, l, co, c in rows]


class EditIn(BaseModel):
    subject: str
    body_text: str


def _get_pending(db: Session, current: CurrentUser, job_id: uuid.UUID) -> SendJob:
    job = db.get(SendJob, job_id)
    if job is None or job.tenant_id != current.tenant_id:
        raise HTTPException(404, "不存在")
    if job.status != "pending_approval":
        raise HTTPException(409, f"状态 {job.status} 不可操作")
    return job


@router.post("/{job_id}/approve", status_code=204)
def approve(job_id: uuid.UUID, body: EditIn | None = None,
            current: CurrentUser = Depends(get_current_user),
            db: Session = Depends(get_tenant_db)) -> None:
    job = _get_pending(db, current, job_id)
    if body is not None and (body.subject or body.body_text):
        # 编辑后通过：人工修改记入 meta（FR-GEN-06 偏好学习的原料）
        job.generation_meta = {**job.generation_meta,
                               "edited": {"subject": job.subject != body.subject,
                                          "body": job.body_text != body.body_text}}
        job.subject, job.body_text = body.subject, body.body_text
    job.status = "approved"
    audit.record(db, current.tenant_id, "send_job", job.id, "send_job.approved",
                 {"edited": bool(body)})
    db.commit()


class RejectIn(BaseModel):
    reason: str = ""


@router.post("/{job_id}/reject", status_code=204)
def reject(job_id: uuid.UUID, body: RejectIn,
           current: CurrentUser = Depends(get_current_user),
           db: Session = Depends(get_tenant_db)) -> None:
    job = _get_pending(db, current, job_id)
    job.status = "rejected"
    state = db.get(SequenceState, job.sequence_state_id)
    state.status = "stopped_manual"
    state.next_action_at = None
    audit.record(db, current.tenant_id, "send_job", job.id, "send_job.rejected",
                 {"reason": body.reason[:200]})
    db.commit()


enroll_router = APIRouter(prefix="/api/campaigns", tags=["sequence"])


class EnrollOut(BaseModel):
    enrolled: int
    skipped: list[str]


@enroll_router.post("/{campaign_id}/enroll-ready", response_model=EnrollOut)
def enroll_ready(campaign_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_tenant_db)) -> EnrollOut:
    """预跑校准完成后：把 ready 线索批量送入序列，任务转 active。"""
    from app.modules.campaign.models import Campaign
    from app.modules.mailbox.models import Mailbox

    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != current.tenant_id:
        raise HTTPException(404, "任务不存在")
    mailbox = db.execute(
        select(Mailbox).where(Mailbox.tenant_id == current.tenant_id,
                              Mailbox.user_id == campaign.owner_user_id)
    ).scalars().first()
    if mailbox is None:
        raise HTTPException(422, "请先在设置中接入发信邮箱")

    leads = db.execute(
        select(Lead).where(Lead.tenant_id == current.tenant_id,
                           Lead.campaign_id == campaign_id, Lead.status == "ready")
    ).scalars().all()
    enrolled, skipped = 0, []
    for lead in leads:
        try:
            _enroll(db, lead, mailbox)
            enrolled += 1
        except EnrollError as e:
            skipped.append(f"{lead.id}: {e}")
    if campaign.status == "dry_run":
        campaign.status = "active"
    db.commit()
    return EnrollOut(enrolled=enrolled, skipped=skipped[:20])
