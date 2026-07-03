"""发信邮箱接入（v0：SMTP/IMAP 通用为主，含常见企业邮箱预设；OAuth 通道二阶段接向导）。"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.core.tenancy import CurrentUser, get_current_user, get_tenant_db
from app.modules.audit import service as audit
from app.modules.mailbox.channels.smtp import SMTP_PRESETS
from app.modules.mailbox.models import Mailbox
from app.modules.mailbox.service import effective_daily_limit, sends_today

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])


class MailboxOut(BaseModel):
    id: str
    email: str
    channel: str
    health: str
    warmup_day: int
    daily_limit: int
    sent_today: int


class SmtpMailboxIn(BaseModel):
    email: EmailStr
    password: str                 # 授权码/应用专用密码（AES-GCM 加密落库）
    preset: str = ""              # aliyun|tencent|zoho|netease|gmail_app_password|…
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_ssl: bool = True
    imap_host: str = ""
    imap_port: int = 993


@router.get("/presets")
def presets() -> dict:
    return SMTP_PRESETS


@router.get("", response_model=list[MailboxOut])
def list_mailboxes(current: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_tenant_db)) -> list[MailboxOut]:
    rows = db.execute(select(Mailbox).where(Mailbox.tenant_id == current.tenant_id)
                      ).scalars().all()
    return [MailboxOut(id=str(m.id), email=m.email, channel=m.channel, health=m.health,
                       warmup_day=m.warmup_day, daily_limit=effective_daily_limit(m),
                       sent_today=sends_today(db, current.tenant_id, m.id)) for m in rows]


@router.post("/smtp", response_model=MailboxOut, status_code=201)
def add_smtp(body: SmtpMailboxIn, current: CurrentUser = Depends(get_current_user),
             db: Session = Depends(get_tenant_db)) -> MailboxOut:
    count = db.execute(select(Mailbox.id).where(Mailbox.tenant_id == current.tenant_id)
                       ).all()
    from app.modules.quota.models import FREE_PLAN_LIMITS
    if len(count) >= FREE_PLAN_LIMITS["mailboxes"]:
        raise HTTPException(422, "免费版限 1 个发信邮箱")

    cfg = dict(SMTP_PRESETS.get(body.preset, {}))
    smtp_host = body.smtp_host or cfg.get("host", "")
    if not smtp_host:
        raise HTTPException(422, "缺少 SMTP 主机（选择预设或手工填写）")
    mailbox = Mailbox(
        tenant_id=current.tenant_id, user_id=current.user_id, email=body.email.lower(),
        channel="smtp_imap",
        credentials_enc=encrypt_secret(body.password),
        smtp_imap_config={
            "smtp_host": smtp_host,
            "smtp_port": body.smtp_port if body.smtp_host else cfg.get("port", 465),
            "smtp_ssl": body.smtp_ssl if body.smtp_host else cfg.get("ssl", True),
            "imap_host": body.imap_host, "imap_port": body.imap_port,
            "preset": body.preset,
        },
        health="warming", warmup_day=0,
        daily_limit=get_settings().send_daily_limit_warming,
    )
    db.add(mailbox)
    db.flush()
    audit.record(db, current.tenant_id, "mailbox", mailbox.id, "mailbox.added",
                 {"channel": "smtp_imap", "preset": body.preset})
    db.commit()
    return MailboxOut(id=str(mailbox.id), email=mailbox.email, channel=mailbox.channel,
                      health=mailbox.health, warmup_day=0,
                      daily_limit=effective_daily_limit(mailbox), sent_today=0)
