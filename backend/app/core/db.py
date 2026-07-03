import uuid
from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import DateTime, Uuid, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantMixin:
    """所有业务表必带 tenant_id；Postgres RLS 策略见 backend/sql/rls.sql。"""

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
