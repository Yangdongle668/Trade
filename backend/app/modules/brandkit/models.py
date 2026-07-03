"""品牌资产库 —— AI 写作唯一事实源（反幻觉的数据基础，ADR-7）。"""
import uuid

from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid
from app.modules.audit.models import JsonB


class BrandAsset(Base, TenantMixin, TimestampMixin):
    __tablename__ = "brand_assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(30))  # company_intro|product|certification|case|faq
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[dict] = mapped_column(JsonB, default=dict)  # 结构化内容，按 kind 约定 schema
    ai_quotable: Mapped[bool] = mapped_column(Boolean, default=True)  # 「AI 可引用」开关
