"""漏斗与送达报表（FR-RPT-01/02 的 v0 版）。"""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenancy import CurrentUser, get_current_user, get_tenant_db
from app.modules.discovery.models import Lead
from app.modules.mailbox.models import Message
from app.modules.sequence.models import SendJob

router = APIRouter(prefix="/api/reports", tags=["reports"])


class FunnelOut(BaseModel):
    leads_total: int
    scored: int
    ready_or_beyond: int
    contacted: int
    replied: int
    hot: int


@router.get("/funnel", response_model=FunnelOut)
def funnel(campaign_id: uuid.UUID | None = None,
           current: CurrentUser = Depends(get_current_user),
           db: Session = Depends(get_tenant_db)) -> FunnelOut:
    q = select(Lead.status, func.count()).where(Lead.tenant_id == current.tenant_id)
    if campaign_id:
        q = q.where(Lead.campaign_id == campaign_id)
    counts = dict(db.execute(q.group_by(Lead.status)).all())

    def total(*statuses: str) -> int:
        return sum(counts.get(s, 0) for s in statuses)

    beyond_ready = ("ready", "in_sequence", "replied", "hot", "nurturing",
                    "rejected", "cooled", "handed_off")
    sent_q = select(func.count()).where(SendJob.tenant_id == current.tenant_id,
                                        SendJob.status == "sent")
    replies_q = select(func.count()).where(Message.tenant_id == current.tenant_id,
                                           Message.direction == "in")
    return FunnelOut(
        leads_total=sum(counts.values()),
        scored=total(*beyond_ready, "scored", "incomplete"),
        ready_or_beyond=total(*beyond_ready),
        contacted=int(db.execute(sent_q).scalar_one()),
        replied=int(db.execute(replies_q).scalar_one()),
        hot=total("hot", "handed_off"),
    )
