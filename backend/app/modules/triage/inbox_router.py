"""收件箱与热线索队列 API（02 文档 P2/P5）。"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.tenancy import CurrentUser, get_current_user, get_tenant_db
from app.modules.ai_gateway.gateway import invoke_json
from app.modules.audit import service as audit
from app.modules.brandkit.models import BrandAsset
from app.modules.contact.models import Contact
from app.modules.discovery.models import Company, Lead
from app.modules.mailbox.channels import get_channel
from app.modules.mailbox.channels.base import OutgoingMail, new_rfc_message_id
from app.modules.mailbox.models import Mailbox, Message, Thread
from app.modules.triage.service import unsubscribe_url

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class ThreadOut(BaseModel):
    id: str
    company_name: str
    domain: str
    contact_name: str
    subject: str
    last_snippet: str
    last_at: str
    classification: str
    lead_status: str
    lead_id: str


@router.get("", response_model=list[ThreadOut])
def list_threads(classification: str = "", current: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_tenant_db)) -> list[ThreadOut]:
    threads = db.execute(
        select(Thread).where(Thread.tenant_id == current.tenant_id)
        .order_by(desc(Thread.updated_at)).limit(100)
    ).scalars().all()
    out = []
    for t in threads:
        last_in = db.execute(
            select(Message).where(Message.thread_id == t.id, Message.direction == "in")
            .order_by(desc(Message.sent_or_received_at))
        ).scalars().first()
        if last_in is None:
            continue  # 收件箱只展示有回复的会话
        if classification and last_in.classification != classification:
            continue
        lead = db.get(Lead, t.lead_id)
        company = db.get(Company, lead.company_id)
        contact = db.get(Contact, t.contact_id)
        out.append(ThreadOut(
            id=str(t.id), company_name=company.name or company.domain, domain=company.domain,
            contact_name=contact.full_name if contact else "",
            subject=t.subject, last_snippet=last_in.body_text[:140],
            last_at=(last_in.sent_or_received_at or datetime.now(timezone.utc)).isoformat(),
            classification=last_in.classification, lead_status=lead.status, lead_id=str(lead.id),
        ))
    # 热线索置顶
    out.sort(key=lambda x: (x.lead_status != "hot", x.last_at), reverse=False)
    return out


class MessageOut(BaseModel):
    direction: str
    subject: str
    body_text: str
    at: str
    classification: str


class ThreadDetailOut(BaseModel):
    id: str
    company_name: str
    domain: str
    contact_name: str
    lead_id: str
    lead_status: str
    messages: list[MessageOut]


def _get_thread(db: Session, current: CurrentUser, thread_id: uuid.UUID) -> Thread:
    t = db.get(Thread, thread_id)
    if t is None or t.tenant_id != current.tenant_id:
        raise HTTPException(404, "会话不存在")
    return t


@router.get("/{thread_id}", response_model=ThreadDetailOut)
def thread_detail(thread_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_tenant_db)) -> ThreadDetailOut:
    t = _get_thread(db, current, thread_id)
    lead = db.get(Lead, t.lead_id)
    company = db.get(Company, lead.company_id)
    contact = db.get(Contact, t.contact_id)
    msgs = db.execute(
        select(Message).where(Message.thread_id == t.id)
        .order_by(Message.sent_or_received_at)
    ).scalars().all()
    return ThreadDetailOut(
        id=str(t.id), company_name=company.name or company.domain, domain=company.domain,
        contact_name=contact.full_name if contact else "", lead_id=str(lead.id),
        lead_status=lead.status,
        messages=[MessageOut(direction=m.direction, subject=m.subject, body_text=m.body_text,
                             at=(m.sent_or_received_at or datetime.now(timezone.utc)).isoformat(),
                             classification=m.classification) for m in msgs],
    )


_REPLY_SYSTEM = """You draft a reply to a prospect's email on behalf of a Chinese exporter's
salesperson. Use ONLY the brand assets for product facts (MOQ, certs, lead time, prices if given).
Address exactly what the prospect asked. Plain text, under 120 words, warm and professional,
sign with the sender name. 输出 JSON: {"body": "…"}"""


class DraftOut(BaseModel):
    body: str


@router.post("/{thread_id}/draft-reply", response_model=DraftOut)
def draft_reply(thread_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_tenant_db)) -> DraftOut:
    t = _get_thread(db, current, thread_id)
    msgs = db.execute(select(Message).where(Message.thread_id == t.id)
                      .order_by(Message.sent_or_received_at)).scalars().all()
    convo = "\n\n".join(f"[{m.direction}] {m.body_text[:800]}" for m in msgs[-4:])
    assets = db.execute(select(BrandAsset).where(BrandAsset.tenant_id == current.tenant_id,
                                                 BrandAsset.ai_quotable.is_(True))
                        ).scalars().all()
    assets_txt = "\n".join(f"- [{a.kind}] {a.title}: " +
                           "; ".join(f"{k}={v}" for k, v in a.content.items())
                           for a in assets) or "- (none)"
    from app.modules.identity.models import User
    user = db.get(User, current.user_id)
    out = invoke_json("draft_reply", _REPLY_SYSTEM,
                      f"Conversation:\n{convo}\n\nBrand assets:\n{assets_txt}\n\n"
                      f"Sender name: {user.display_name or 'Sales'}",
                      max_tokens=400)
    return DraftOut(body=str(out.get("body", "")).strip())


class SendReplyIn(BaseModel):
    body: str


@router.post("/{thread_id}/send-reply", status_code=204)
def send_reply(thread_id: uuid.UUID, body: SendReplyIn,
               current: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_tenant_db)) -> None:
    """人工确认后的直发回信（不走序列，不占开发信日限之外的护栏）。"""
    t = _get_thread(db, current, thread_id)
    last_in = db.execute(
        select(Message).where(Message.thread_id == t.id, Message.direction == "in")
        .order_by(desc(Message.sent_or_received_at))
    ).scalars().first()
    if last_in is None:
        raise HTTPException(409, "该会话没有可回复的来信")
    mailbox = db.execute(
        select(Mailbox).where(Mailbox.tenant_id == current.tenant_id,
                              Mailbox.user_id == current.user_id,
                              Mailbox.health != "paused")
    ).scalars().first()
    if mailbox is None:
        raise HTTPException(422, "无可用发信邮箱")
    from app.modules.contact.models import EmailCandidate
    to_email = db.execute(
        select(EmailCandidate.email).where(EmailCandidate.tenant_id == current.tenant_id,
                                           EmailCandidate.contact_id == t.contact_id)
    ).scalars().first()
    if to_email is None:
        raise HTTPException(422, "联系人无邮箱")

    mail = OutgoingMail(
        to_email=to_email, subject=f"Re: {last_in.subject or t.subject}",
        body_text=body.body,
        rfc_message_id=new_rfc_message_id(mailbox.email.split("@")[-1]),
        in_reply_to=last_in.rfc_message_id,
        unsubscribe_url=unsubscribe_url(current.tenant_id, to_email),
    )
    get_channel(mailbox.channel).send(mailbox, mail)
    db.add(Message(tenant_id=current.tenant_id, thread_id=t.id, mailbox_id=mailbox.id,
                   direction="out", rfc_message_id=mail.rfc_message_id,
                   in_reply_to=last_in.rfc_message_id, subject=mail.subject,
                   body_text=body.body, sent_or_received_at=datetime.now(timezone.utc)))
    lead = db.get(Lead, t.lead_id)
    if lead.status == "hot":
        lead.status = "handed_off"
        audit.record(db, current.tenant_id, "lead", lead.id, "lead.handed_off",
                     {"thread_id": str(t.id)})
    db.commit()
