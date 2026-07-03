"""联系人处理（流水线 contacts+verify 阶段，架构 §5.1）。

输入：研判产出的 contacts_hint（姓名/职位）+ 公司域名
输出：Contact + EmailCandidate（已验证、带置信度）；
      线索状态 → ready（有可发邮箱）或 incomplete（待补全，定期重试）。
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.contact.models import Contact, EmailCandidate
from app.modules.contact.patterns import generate_email_patterns, generic_candidates
from app.modules.contact.verifier import verify_email

MAX_PATTERN_TRIES = 4   # 每人最多验证前 N 个模式（控制 SMTP 验证量）
SENDABLE = {"high", "medium"}


def process_lead_contacts(db: Session, tenant_id: uuid.UUID, company_id: uuid.UUID,
                          domain: str, contacts_hint: list[dict]) -> bool:
    """返回是否找到至少一个可发送邮箱（决定 lead ready/incomplete）。"""
    found_sendable = False

    for hint in contacts_hint[:5]:
        name = str(hint.get("name", "")).strip()
        if not name:
            continue
        contact = _get_or_create_contact(db, tenant_id, company_id, name,
                                         str(hint.get("title", "")))
        for email in generate_email_patterns(name, domain)[:MAX_PATTERN_TRIES]:
            result = verify_email(email)
            if result.confidence == "invalid":
                continue
            _add_candidate(db, tenant_id, contact.id, email, "pattern", result)
            if result.confidence in SENDABLE:
                found_sendable = True
                break  # 该联系人已有可用邮箱，停止尝试后续模式

    if not found_sendable:
        # 兜底：公司公共邮箱（low 置信度，仅供人工参考，不进发送队列）
        contact = _get_or_create_contact(db, tenant_id, company_id, "", "General inbox")
        for email in generic_candidates(domain)[:2]:
            result = verify_email(email)
            if result.confidence != "invalid":
                _add_candidate(db, tenant_id, contact.id, email, "generic", result)
    return found_sendable


def _get_or_create_contact(db: Session, tenant_id: uuid.UUID, company_id: uuid.UUID,
                           name: str, title: str) -> Contact:
    q = select(Contact).where(Contact.tenant_id == tenant_id,
                              Contact.company_id == company_id,
                              Contact.full_name == name)
    existing = db.execute(q).scalars().first()
    if existing:
        return existing
    contact = Contact(tenant_id=tenant_id, company_id=company_id, full_name=name,
                      role_title=title, source="website",
                      source_note="AI 从公司官网公开页面提取")
    db.add(contact)
    db.flush()
    return contact


def _add_candidate(db: Session, tenant_id: uuid.UUID, contact_id: uuid.UUID,
                   email: str, method: str, result) -> None:
    exists = db.execute(
        select(EmailCandidate.id).where(EmailCandidate.tenant_id == tenant_id,
                                        EmailCandidate.contact_id == contact_id,
                                        EmailCandidate.email == email)
    ).first()
    if exists:
        return
    db.add(EmailCandidate(tenant_id=tenant_id, contact_id=contact_id, email=email,
                          method=method, confidence=result.confidence,
                          verify_status=result.status))
