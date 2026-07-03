"""压制名单与退订（FR-RPL-05）：命中即永不触达，发送路径强制校验。"""
import base64
import hashlib
import hmac
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit import service as audit
from app.modules.triage.models import SuppressionEntry


def is_suppressed(db: Session, tenant_id: uuid.UUID, email: str) -> bool:
    email = email.lower()
    domain_part = "@" + email.split("@")[-1]
    hit = db.execute(
        select(SuppressionEntry.id).where(
            SuppressionEntry.tenant_id == tenant_id,
            SuppressionEntry.value.in_([email, domain_part]))
    ).first()
    return hit is not None


def add_suppression(db: Session, tenant_id: uuid.UUID, email: str, reason: str,
                    note: str = "") -> None:
    email = email.lower()
    if is_suppressed(db, tenant_id, email):
        return
    entry = SuppressionEntry(tenant_id=tenant_id, value=email, kind="email",
                             reason=reason, source_note=note)
    db.add(entry)
    db.flush()
    audit.record(db, tenant_id, "suppression", entry.id, "suppression.added",
                 {"reason": reason})
    # 停掉该邮箱对应联系人的所有在途序列（不变量 1 的压制侧）
    from app.modules.contact.models import EmailCandidate
    from app.modules.sequence.service import stop_sequences_for_contacts
    contact_ids = db.execute(
        select(EmailCandidate.contact_id).where(EmailCandidate.tenant_id == tenant_id,
                                                EmailCandidate.email == email)
    ).scalars().all()
    if contact_ids:
        stop_sequences_for_contacts(db, tenant_id, contact_ids, "suppressed")


# ---- 退订签名链接（无需登录，架构 §7）----

def unsubscribe_token(tenant_id: uuid.UUID, email: str) -> str:
    payload = f"{tenant_id}:{email.lower()}"
    sig = hmac.new(get_settings().secret_key.encode(), payload.encode(),
                   hashlib.sha256).hexdigest()[:24]
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def parse_unsubscribe_token(token: str) -> tuple[uuid.UUID, str] | None:
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        tenant_s, email, sig = payload.rsplit(":", 2)
        expected = hmac.new(get_settings().secret_key.encode(),
                            f"{tenant_s}:{email}".encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected):
            return None
        return uuid.UUID(tenant_s), email
    except Exception:
        return None


def unsubscribe_url(tenant_id: uuid.UUID, email: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/api/u/{unsubscribe_token(tenant_id, email)}"
