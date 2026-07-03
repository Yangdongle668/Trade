import uuid

from sqlalchemy import Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid

# 免费版 v0 配额（04 文档 §5）
FREE_PLAN_LIMITS = {
    "leads_per_month": 100,        # 已研判线索
    "generations_per_month": 300,  # AI 生成（平台代付模式）
    "mailboxes": 1,
    "seats": 1,
}


class UsageCounter(Base, TenantMixin, TimestampMixin):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("tenant_id", "metric", "period"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    metric: Mapped[str] = mapped_column(String(40))   # leads|generations|sends|pse_queries|...
    period: Mapped[str] = mapped_column(String(10))   # YYYY-MM 或 YYYY-MM-DD（源配额按日）
    used: Mapped[int] = mapped_column(Integer, default=0)
