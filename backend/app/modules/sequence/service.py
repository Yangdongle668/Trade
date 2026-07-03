"""序列引擎（架构 §6）。

生命周期：enroll → [tick: 生成 send_job(幂等) + 排窗口] → 审批(按自动化级别)
        → [tick: 到点投递执行] → execute(三重校验) → 发送 → 推进下一步/完成。
"""
import random
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.campaign.models import Campaign
from app.modules.contact.models import Contact, EmailCandidate
from app.modules.discovery.models import Company, Lead
from app.modules.mailbox.channels import get_channel
from app.modules.mailbox.channels.base import HardBounceError, OutgoingMail, new_rfc_message_id
from app.modules.mailbox.models import Mailbox
from app.modules.mailbox.service import can_send, record_hard_bounce, record_send
from app.modules.sequence.generator import generate_email
from app.modules.sequence.models import SendJob, SequenceState
from app.modules.sequence.windows import next_send_time, resolve_timezone
from app.modules.triage.service import is_suppressed, unsubscribe_url

log = structlog.get_logger()

DEFAULT_SEQUENCE = [
    {"day": 0, "angle": "intro"},
    {"day": 3, "angle": "case"},
    {"day": 8, "angle": "insight"},
    {"day": 15, "angle": "breakup"},
]
GLOBAL_FREQUENCY_DAYS = 30  # 不变量 3：同联系人 30 天内只进 1 个序列
SENDABLE_CONFIDENCE = ("high", "medium")


class EnrollError(Exception):
    pass


def _steps(campaign: Campaign) -> list[dict]:
    return campaign.playbook.get("sequence") or DEFAULT_SEQUENCE


def _sendable_email(db: Session, tenant_id: uuid.UUID, contact_id: uuid.UUID) -> str | None:
    row = db.execute(
        select(EmailCandidate.email).where(
            EmailCandidate.tenant_id == tenant_id,
            EmailCandidate.contact_id == contact_id,
            EmailCandidate.confidence.in_(SENDABLE_CONFIDENCE))
        .order_by(EmailCandidate.confidence)  # high < medium 字典序，恰好优先 high… 显式排序：
    ).scalars().all()
    for email in row:
        return email
    return None


def enroll_lead(db: Session, lead: Lead, mailbox: Mailbox) -> SequenceState:
    """ready 线索进入序列。校验：可发邮箱、压制名单、30 天全局频控。"""
    if lead.status != "ready":
        raise EnrollError(f"线索状态 {lead.status} 不能进入序列")
    campaign = db.get(Campaign, lead.campaign_id)
    company = db.get(Company, lead.company_id)
    contact = db.execute(
        select(Contact).where(Contact.tenant_id == lead.tenant_id,
                              Contact.company_id == lead.company_id,
                              Contact.full_name != "")
    ).scalars().first()
    if contact is None:
        raise EnrollError("无具名联系人")
    email = _sendable_email(db, lead.tenant_id, contact.id)
    if email is None:
        raise EnrollError("无可发送邮箱（置信度不足）")
    if is_suppressed(db, lead.tenant_id, email):
        raise EnrollError("联系人在压制名单中")

    # 不变量 3：全局频控
    recent = db.execute(
        select(SequenceState).where(
            SequenceState.tenant_id == lead.tenant_id,
            SequenceState.contact_id == contact.id,
            SequenceState.created_at > datetime.now(timezone.utc) - timedelta(days=GLOBAL_FREQUENCY_DAYS))
    ).first()
    if recent:
        raise EnrollError(f"该联系人 {GLOBAL_FREQUENCY_DAYS} 天内已在其他序列中")

    state = SequenceState(
        tenant_id=lead.tenant_id, contact_id=contact.id, campaign_id=campaign.id,
        lead_id=lead.id, current_step=0, status="active",
        next_action_at=datetime.now(timezone.utc),
        timezone=resolve_timezone(contact.timezone, company.country),
    )
    db.add(state)
    lead.status = "in_sequence"
    db.flush()
    audit.record(db, lead.tenant_id, "sequence", state.id, "sequence.enrolled",
                 {"lead_id": str(lead.id), "email": email})
    return state


def tick(db: Session, now: datetime | None = None, limit: int = 50) -> dict:
    """beat 每 5 分钟调用：① 到点序列生成 send_job；② 到点已批准 job 投递执行。"""
    now = now or datetime.now(timezone.utc)
    stats = {"jobs_created": 0, "jobs_dispatched": 0}

    due_states = db.execute(
        select(SequenceState).where(SequenceState.status == "active",
                                    SequenceState.next_action_at <= now)
        .limit(limit).with_for_update(skip_locked=True)
    ).scalars().all()
    for state in due_states:
        if _create_send_job(db, state, now):
            stats["jobs_created"] += 1
    db.commit()

    due_jobs = db.execute(
        select(SendJob).where(SendJob.status == "approved", SendJob.scheduled_at <= now)
        .limit(limit).with_for_update(skip_locked=True)
    ).scalars().all()
    for job in due_jobs:
        job.status = "queued"
        stats["jobs_dispatched"] += 1
    db.commit()
    for job in due_jobs:
        from app.modules.sequence.tasks import execute_send_job
        execute_send_job.delay(str(job.id))
    return stats


def _create_send_job(db: Session, state: SequenceState, now: datetime) -> bool:
    campaign = db.get(Campaign, state.campaign_id)
    steps = _steps(campaign)
    if state.current_step >= len(steps):
        state.status = "completed"
        return False
    step = steps[state.current_step]
    idem = f"{state.id}:{state.current_step}"
    if db.execute(select(SendJob.id).where(SendJob.idempotency_key == idem)).first():
        state.next_action_at = None  # job 已存在（不变量 2 兜底），等待其完成
        return False

    lead = db.get(Lead, state.lead_id)
    company = db.get(Company, lead.company_id)
    mailbox = _pick_mailbox(db, state.tenant_id, campaign.owner_user_id)
    if mailbox is None:
        state.next_action_at = now + timedelta(hours=6)  # 无可用发信身份，稍后重试
        return False

    # 写信（反幻觉+反垃圾闸门，最多重试 2 次）
    sender = _sender_name(db, campaign.owner_user_id)
    draft = None
    for _ in range(2):
        draft = generate_email(db, state.tenant_id, company, step.get("angle", "intro"), sender)
        if draft.ok:
            break
    if draft is None or not draft.ok:
        state.next_action_at = now + timedelta(hours=12)
        audit.record(db, state.tenant_id, "sequence", state.id, "draft.rejected",
                     {"violations": (draft.violations if draft else ["generation_failed"])[:5]})
        return False

    # 自动化级别（02 文档 §5.2）
    if campaign.automation_level == "per_email":
        status = "pending_approval"
    elif campaign.automation_level == "sampling":
        status = "pending_approval" if random.random() * 100 < campaign.sampling_rate else "approved"
    else:
        status = "approved"

    job = SendJob(
        tenant_id=state.tenant_id, sequence_state_id=state.id, step_no=state.current_step,
        idempotency_key=idem, mailbox_id=mailbox.id,
        scheduled_at=next_send_time(state.timezone, now),
        status=status, subject=draft.subject, body_text=draft.body,
        generation_meta={"angle": step.get("angle"), "fact_urls": draft.used_fact_urls},
    )
    db.add(job)
    db.flush()  # 先拿到 job.id 再写审计
    state.next_action_at = None  # 等待 job 走完再推进
    audit.record(db, state.tenant_id, "send_job", job.id, f"send_job.{status}",
                 {"step": state.current_step})
    return True


def execute_send(db: Session, job_id: uuid.UUID) -> str:
    """三重校验后发送（架构 §6.1）。返回结果字符串供日志。"""
    job = db.execute(select(SendJob).where(SendJob.id == job_id)
                     .with_for_update()).scalar_one_or_none()
    if job is None or job.status not in ("queued", "approved"):
        return "skip:job_state"
    state = db.get(SequenceState, job.sequence_state_id)
    contact_email = _sendable_email(db, job.tenant_id, state.contact_id)

    # ① 压制名单 ② 序列状态复查（竞态兜底） ③ 发信健康与日限
    if contact_email is None or is_suppressed(db, job.tenant_id, contact_email):
        job.status = "canceled"
        state.status = "suppressed"
        db.commit()
        return "canceled:suppressed"
    if state.status != "active":
        job.status = "canceled"
        db.commit()
        return "canceled:sequence_stopped"
    mailbox = db.get(Mailbox, job.mailbox_id)
    ok, why = can_send(db, mailbox)
    if not ok:
        job.scheduled_at = datetime.now(timezone.utc) + timedelta(hours=4)
        job.status = "approved"  # 回到待投递，明日窗口重试
        db.commit()
        return f"deferred:{why}"

    lead = db.get(Lead, state.lead_id)
    company = db.get(Company, lead.company_id)
    mail = OutgoingMail(
        to_email=contact_email, subject=job.subject, body_text=job.body_text,
        rfc_message_id=new_rfc_message_id(mailbox.email.split("@")[-1]),
        unsubscribe_url=unsubscribe_url(job.tenant_id, contact_email),
        footer=_footer(db, job.tenant_id),
    )
    try:
        get_channel(mailbox.channel).send(mailbox, mail)
    except HardBounceError as e:
        job.status = "failed"
        from app.modules.triage.service import add_suppression
        add_suppression(db, job.tenant_id, contact_email, "hard_bounce", str(e)[:200])
        record_hard_bounce(db, mailbox)
        db.commit()
        return "failed:hard_bounce"
    except Exception as e:
        job.status = "approved"
        job.scheduled_at = datetime.now(timezone.utc) + timedelta(hours=2)
        db.commit()
        log.warning("send.retry_later", job=str(job.id), error=str(e))
        return "deferred:channel_error"

    job.status, job.message_id = "sent", mail.rfc_message_id
    record_send(db, mailbox)
    _record_message(db, job, state, lead, mailbox, mail, company)
    # 推进序列
    campaign = db.get(Campaign, state.campaign_id)
    steps = _steps(campaign)
    state.current_step += 1
    if state.current_step >= len(steps):
        state.status = "completed"
        state.next_action_at = None
    else:
        delay = steps[state.current_step]["day"] - steps[state.current_step - 1]["day"]
        state.next_action_at = datetime.now(timezone.utc) + timedelta(days=max(delay, 1))
    audit.record(db, job.tenant_id, "send_job", job.id, "send_job.sent",
                 {"to": contact_email, "step": job.step_no})
    db.commit()
    return "sent"


def stop_sequences_for_contacts(db: Session, tenant_id: uuid.UUID,
                                contact_ids: list, reason: str) -> int:
    """不变量 1：回复/压制 → 取消该联系人所有在途步骤（事务内）。"""
    states = db.execute(
        select(SequenceState).where(SequenceState.tenant_id == tenant_id,
                                    SequenceState.contact_id.in_(contact_ids),
                                    SequenceState.status == "active")
    ).scalars().all()
    for state in states:
        state.status = "stopped_replied" if reason == "replied" else "suppressed"
        state.next_action_at = None
        jobs = db.execute(
            select(SendJob).where(SendJob.sequence_state_id == state.id,
                                  SendJob.status.in_(["pending_approval", "approved", "queued"]))
        ).scalars().all()
        for job in jobs:
            job.status = "canceled"
        audit.record(db, tenant_id, "sequence", state.id, f"sequence.stopped_{reason}",
                     {"canceled_jobs": len(jobs)})
    return len(states)


def _pick_mailbox(db: Session, tenant_id: uuid.UUID, owner_user_id: uuid.UUID) -> Mailbox | None:
    rows = db.execute(
        select(Mailbox).where(Mailbox.tenant_id == tenant_id,
                              Mailbox.user_id == owner_user_id,
                              Mailbox.health.in_(["healthy", "warming"]))
    ).scalars().all()
    for mb in rows:
        ok, _ = can_send(db, mb)
        if ok:
            return mb
    return None


def _sender_name(db: Session, user_id: uuid.UUID) -> str:
    from app.modules.identity.models import User
    user = db.get(User, user_id)
    return (user.display_name or user.email.split("@")[0]) if user else "Sales"


def _footer(db: Session, tenant_id: uuid.UUID) -> str:
    from app.modules.identity.models import Tenant
    tenant = db.get(Tenant, tenant_id)
    return tenant.name if tenant else ""


def _record_message(db, job, state, lead, mailbox, mail, company) -> None:
    from app.modules.mailbox.models import Message, Thread
    thread = db.execute(
        select(Thread).where(Thread.tenant_id == job.tenant_id,
                             Thread.lead_id == lead.id,
                             Thread.contact_id == state.contact_id)
    ).scalars().first()
    if thread is None:
        thread = Thread(tenant_id=job.tenant_id, lead_id=lead.id,
                        contact_id=state.contact_id, subject=mail.subject)
        db.add(thread)
        db.flush()
    db.add(Message(tenant_id=job.tenant_id, thread_id=thread.id, mailbox_id=mailbox.id,
                   direction="out", rfc_message_id=mail.rfc_message_id,
                   subject=mail.subject, body_text=mail.body_text,
                   sent_or_received_at=datetime.now(timezone.utc)))
