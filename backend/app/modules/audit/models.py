"""append-only 事件表：线索全生命周期可回放（架构 §4.2 / NFR 可观测）。"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base, TenantMixin, new_uuid

JsonB = JSON().with_variant(JSONB(), "postgresql")


class Event(Base, TenantMixin):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(40))   # lead / sequence / mailbox / ...
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    event: Mapped[str] = mapped_column(String(80))          # lead.scored / send.approved / ...
    payload: Mapped[dict] = mapped_column(JsonB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
