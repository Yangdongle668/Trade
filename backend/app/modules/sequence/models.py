"""序列引擎数据模型 —— 全系统可靠性要求最高的模块（架构 §6）。

四条不变量的数据库层落点：
1. 回复即全停：sequence_states.status 置 stopped + 取消 pending send_jobs（事务内）
2. 绝不重发：send_jobs.idempotency_key 唯一约束（物理保证）
3. 全局频控：UNIQUE(contact_id, campaign_id) + 建序列前 30 天检查
4. 时区窗口：scheduled_at 由联系人时区计算，窗口外只排队
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid
from app.modules.audit.models import JsonB


class SequenceState(Base, TenantMixin, TimestampMixin):
    __tablename__ = "sequence_states"
    __table_args__ = (
        UniqueConstraint("contact_id", "campaign_id"),
        Index("ix_seq_due", "status", "next_action_at"),  # tick 的扫描索引
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    # active | stopped_replied | stopped_manual | completed | suppressed
    status: Mapped[str] = mapped_column(String(20), default="active")
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")


class SendJob(Base, TenantMixin, TimestampMixin):
    __tablename__ = "send_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    sequence_state_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    step_no: Mapped[int] = mapped_column(Integer)
    # 幂等键 = f"{sequence_state_id}:{step_no}" —— 数据库层杜绝重发（ADR-6）
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # pending_approval | approved | queued | sent | canceled | failed | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body_text: Mapped[str] = mapped_column(String(8000), default="")
    generation_meta: Mapped[dict] = mapped_column(JsonB, default=dict)  # 引用的事实/资产 id、spam 检查结果
    message_id: Mapped[str] = mapped_column(String(255), default="")    # 发出后的 RFC Message-ID
