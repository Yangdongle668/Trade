import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid


class Contact(Base, TenantMixin, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    role_title: Mapped[str] = mapped_column(String(200), default="")
    timezone: Mapped[str] = mapped_column(String(50), default="")   # IANA，投递窗口计算用
    source: Mapped[str] = mapped_column(String(50), default="")     # website|companies_house|manual
    source_note: Mapped[str] = mapped_column(String(500), default="")  # GDPR：来源与采集说明


class EmailCandidate(Base, TenantMixin, TimestampMixin):
    __tablename__ = "email_candidates"
    __table_args__ = (UniqueConstraint("tenant_id", "contact_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    email: Mapped[str] = mapped_column(String(320))
    method: Mapped[str] = mapped_column(String(30), default="pattern")  # pattern|website|registry
    # 置信度分级（03 文档 S7）：high|medium|low|catch_all|invalid
    # 铁律：非 high/medium 不进发送队列（FR-CNT-02）
    confidence: Mapped[str] = mapped_column(String(15), default="low")
    verify_status: Mapped[str] = mapped_column(String(20), default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
