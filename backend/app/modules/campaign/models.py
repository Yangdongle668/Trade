import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TenantMixin, TimestampMixin, new_uuid
from app.modules.audit.models import JsonB


class Campaign(Base, TenantMixin, TimestampMixin):
    """开发任务 = ICP + 话术策略 + 自动化级别（02 文档 §4）。"""

    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # draft → dry_run（预跑确认，02 文档 §5.3）→ active → paused → archived
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # 逐封审批 per_email | 抽检 sampling | 全自动 full_auto
    automation_level: Mapped[str] = mapped_column(String(20), default="per_email")
    sampling_rate: Mapped[int] = mapped_column(default=20)  # 抽检百分比

    icp: Mapped[dict] = mapped_column(JsonB, default=dict)
    # {countries:["US","GB"], industry_keywords:[...], company_types:[...],
    #  size_hint:"", freeform:"要有实体门店，不要纯电商", exclusions:[...]}
    playbook: Mapped[dict] = mapped_column(JsonB, default=dict)
    # {value_props:[asset_id...], sequence:[{day:0,angle:"intro",ab:["subjA","subjB"]},
    #  {day:3,angle:"case"},{day:8,angle:"insight"},{day:15,angle:"breakup"}]}
