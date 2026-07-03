"""入向邮件处理（价值兑现点，02 文档 §5.6）。

流程：归属（线程/联系人）→ 去重 → 落库 → AI 分类
    → 序列停止（auto_reply 除外）→ 线索状态流转 → 热线索事件。
分类低置信度 → unclassified 转人工分拣（热线索漏报率趋零：宁可多推给人）。
"""
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai_gateway.gateway import AIGatewayError, invoke_json
from app.modules.audit import service as audit
from app.modules.contact.models import Contact, EmailCandidate
from app.modules.discovery.models import Lead
from app.modules.mailbox.inbound import InboundMail
from app.modules.mailbox.models import Mailbox, Message, Thread
from app.modules.sequence.service import stop_sequences_for_contacts
from app.modules.triage.service import add_suppression

log = structlog.get_logger()

CLASSIFICATIONS = ("interested", "question", "later", "rejected",
                   "unsubscribe", "auto_reply", "referral", "unclassified")
HOT = {"interested", "question"}
MIN_CONFIDENCE = 70

_CLASSIFY_SYSTEM = """You classify replies to B2B cold-outreach emails. Categories:
interested（索要报价/目录/样品/明确兴趣）| question（有疑问需解答）|
later（现在不需要，将来再说，可能带时间）| rejected（明确拒绝/已有供应商）|
unsubscribe（要求停止发送/移除）| auto_reply（外出自动回复/系统通知）|
referral（转介绍给他人）
输出 JSON: {"category": "…", "confidence": 0-100, "summary_zh": "一句中文摘要"}"""

UNSUB_KEYWORDS = ("unsubscribe", "remove me", "stop emailing", "take me off")


def process_inbound(db: Session, mailbox: Mailbox, mail: InboundMail) -> str:
    tenant_id = mailbox.tenant_id
    # 去重（同一封信多次拉取）
    if mail.rfc_message_id and db.execute(
        select(Message.id).where(Message.tenant_id == tenant_id,
                                 Message.rfc_message_id == mail.rfc_message_id)
    ).first():
        return "dup"

    thread, contact_id = _attribute(db, tenant_id, mail)
    if thread is None:
        return "unmatched"  # 非本系统触达对象的来信，不处理

    msg = Message(
        tenant_id=tenant_id, thread_id=thread.id, mailbox_id=mailbox.id, direction="in",
        rfc_message_id=mail.rfc_message_id, in_reply_to=mail.in_reply_to,
        subject=mail.subject, body_text=mail.body_text,
        sent_or_received_at=mail.received_at,
    )
    db.add(msg)
    db.flush()

    category, confidence, summary = _classify(mail)
    msg.classification, msg.classification_confidence = category, confidence

    lead = db.get(Lead, thread.lead_id)
    if category == "unsubscribe" or any(k in mail.body_text.lower() for k in UNSUB_KEYWORDS):
        msg.classification = "unsubscribe"
        add_suppression(db, tenant_id, mail.from_email, "unsubscribe", "回信要求退订")
        lead.status = "rejected"
    elif category == "auto_reply":
        pass  # 自动回复不停序列、不改状态
    else:
        stop_sequences_for_contacts(db, tenant_id, [contact_id], "replied")
        if category in HOT:
            lead.status = "hot"
            audit.record(db, tenant_id, "lead", lead.id, "lead.hot",
                         {"summary": summary, "thread_id": str(thread.id)})
        elif category == "later":
            lead.status = "nurturing"
        elif category == "rejected":
            lead.status = "rejected"
        else:  # referral / unclassified → 人工分拣，保守置为 replied
            lead.status = "replied"

    audit.record(db, tenant_id, "message", msg.id, f"reply.{msg.classification}",
                 {"confidence": confidence, "summary": summary})
    db.commit()
    return msg.classification


def _attribute(db: Session, tenant_id: uuid.UUID,
               mail: InboundMail) -> tuple[Thread | None, uuid.UUID | None]:
    """归属优先级：In-Reply-To/References 线程匹配 > 发件人邮箱匹配联系人。"""
    ref_ids = [r for r in ([mail.in_reply_to] + mail.references) if r]
    if ref_ids:
        row = db.execute(
            select(Message).where(Message.tenant_id == tenant_id,
                                  Message.rfc_message_id.in_(ref_ids))
        ).scalars().first()
        if row is not None:
            thread = db.get(Thread, row.thread_id)
            return thread, thread.contact_id
    cand = db.execute(
        select(EmailCandidate).where(EmailCandidate.tenant_id == tenant_id,
                                     EmailCandidate.email == mail.from_email)
    ).scalars().first()
    if cand is not None:
        thread = db.execute(
            select(Thread).where(Thread.tenant_id == tenant_id,
                                 Thread.contact_id == cand.contact_id)
        ).scalars().first()
        if thread is not None:
            return thread, cand.contact_id
    return None, None


def _classify(mail: InboundMail) -> tuple[str, int, str]:
    try:
        out = invoke_json("classify_reply", _CLASSIFY_SYSTEM,
                          f"Subject: {mail.subject}\n\n{mail.body_text[:3000]}",
                          max_tokens=200)
        category = str(out.get("category", "")).strip()
        confidence = int(out.get("confidence", 0))
        summary = str(out.get("summary_zh", ""))[:200]
        if category not in CLASSIFICATIONS or confidence < MIN_CONFIDENCE:
            return "unclassified", confidence, summary
        return category, confidence, summary
    except (AIGatewayError, ValueError) as e:
        log.warning("classify.failed", error=str(e))
        return "unclassified", 0, ""
