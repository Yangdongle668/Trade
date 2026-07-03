import uuid

from sqlalchemy import String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid


class SuppressionEntry(Base, TenantMixin, TimestampMixin):
    """租户级压制名单：命中即永不触达（终态，不可逆）。发送路径强制校验（架构 §6.1 ②）。"""

    __tablename__ = "suppression_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "value"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    value: Mapped[str] = mapped_column(String(320))     # 邮箱或 @domain
    kind: Mapped[str] = mapped_column(String(10), default="email")  # email | domain
    reason: Mapped[str] = mapped_column(String(30))     # unsubscribe|complaint|hard_bounce|manual|gdpr
    source_note: Mapped[str] = mapped_column(String(500), default="")
