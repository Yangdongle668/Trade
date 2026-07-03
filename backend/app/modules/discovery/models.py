import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid
from app.modules.audit.models import JsonB

LEAD_STATUSES = (
    "discovered", "scored", "ready", "incomplete", "in_sequence", "replied",
    "hot", "nurturing", "rejected", "cooled", "handed_off", "suppressed", "excluded",
)


class Company(Base, TenantMixin, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("tenant_id", "domain"),)  # 去重/撞单唯一键

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    domain: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), default="")
    country: Mapped[str] = mapped_column(String(2), default="")  # ISO 3166-1
    city: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[str] = mapped_column(String(30), default="")  # pse|maps|companies_house|manual
    meta: Mapped[dict] = mapped_column(JsonB, default=dict)      # 地址/电话/评论数等源侧原始信号


class Lead(Base, TenantMixin, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "campaign_id"),
        Index("ix_leads_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(20), default="discovered")
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_reason: Mapped[str] = mapped_column(Text, default="")  # AI 一句话理由（D3 可解释）


class ResearchFact(Base, TimestampMixin):
    """公司公开事实：跨租户共享缓存（联系人数据绝不入此表，架构 §5.2）。
    source_url 非空 = 反幻觉的数据层约束（每条事实必有出处）。"""

    __tablename__ = "research_facts"
    __table_args__ = (Index("ix_facts_domain", "domain"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    domain: Mapped[str] = mapped_column(String(255))
    fact_text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # fetched+90d


class SourceRun(Base, TenantMixin, TimestampMixin):
    """一次数据源适配器执行的记账：免费配额调度与熔断的依据（架构 §5.2）。"""

    __tablename__ = "source_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    adapter: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|done|failed|quota_exhausted
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[dict] = mapped_column(JsonB, default=dict)
