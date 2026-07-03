import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid
from app.modules.audit.models import JsonB


class Mailbox(Base, TenantMixin, TimestampMixin):
    """发信身份。健康状态机（架构 §6.3）：warming → healthy → throttled → paused。"""

    __tablename__ = "mailboxes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    email: Mapped[str] = mapped_column(String(320))
    # gmail | ms_graph | smtp_imap（三通道，ADR-8）
    channel: Mapped[str] = mapped_column(String(20))
    credentials_enc: Mapped[str] = mapped_column(Text)  # AES-GCM：refresh_token 或 SMTP/IMAP 授权码
    smtp_imap_config: Mapped[dict] = mapped_column(JsonB, default=dict)  # host/port/ssl 预设
    health: Mapped[str] = mapped_column(String(20), default="warming")
    warmup_day: Mapped[int] = mapped_column(Integer, default=0)   # 预热第 N/21 天
    daily_limit: Mapped[int] = mapped_column(Integer, default=5)
    # 收件游标：gmail historyId / graph deltaLink / imap {uidvalidity, uidnext}
    poll_cursor: Mapped[dict] = mapped_column(JsonB, default=dict)


class Thread(Base, TenantMixin, TimestampMixin):
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    subject: Mapped[str] = mapped_column(String(500), default="")


class Message(Base, TenantMixin, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_msg_rfc_id", "rfc_message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    direction: Mapped[str] = mapped_column(String(10))  # out | in
    rfc_message_id: Mapped[str] = mapped_column(String(255), default="")
    in_reply_to: Mapped[str] = mapped_column(String(255), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    sent_or_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 入向分类（triage）：interested|question|later|rejected|unsubscribe|auto_reply|referral|unclassified
    classification: Mapped[str] = mapped_column(String(20), default="")
    classification_confidence: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
