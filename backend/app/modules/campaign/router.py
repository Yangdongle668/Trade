import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import CurrentUser, get_current_user, get_tenant_db
from app.modules.audit import service as audit
from app.modules.campaign.models import Campaign
from app.modules.discovery.models import Company, Lead

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

AUTOMATION_LEVELS = {"per_email", "sampling", "full_auto"}


class CampaignIn(BaseModel):
    name: str
    icp: dict = {}
    playbook: dict = {}
    automation_level: str = "per_email"
    sampling_rate: int = 20


class CampaignOut(CampaignIn):
    id: str
    status: str


def _out(c: Campaign) -> CampaignOut:
    return CampaignOut(id=str(c.id), name=c.name, icp=c.icp, playbook=c.playbook,
                       automation_level=c.automation_level, sampling_rate=c.sampling_rate,
                       status=c.status)


@router.get("", response_model=list[CampaignOut])
def list_campaigns(current: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_tenant_db)) -> list[CampaignOut]:
    rows = db.execute(select(Campaign).where(Campaign.tenant_id == current.tenant_id)
                      .order_by(Campaign.created_at.desc())).scalars().all()
    return [_out(c) for c in rows]


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(body: CampaignIn, current: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_tenant_db)) -> CampaignOut:
    if body.automation_level not in AUTOMATION_LEVELS:
        raise HTTPException(422, f"automation_level 必须是 {sorted(AUTOMATION_LEVELS)} 之一")
    c = Campaign(tenant_id=current.tenant_id, owner_user_id=current.user_id, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, current.tenant_id, "campaign", c.id, "campaign.created", {"name": c.name})
    db.commit()
    return _out(c)


@router.post("/{campaign_id}/start-dry-run", response_model=CampaignOut)
def start_dry_run(campaign_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_tenant_db)) -> CampaignOut:
    """预跑（02 文档 §5.3）：先出样本线索供校准，再正式启动。"""
    c = db.get(Campaign, campaign_id)
    if c is None or c.tenant_id != current.tenant_id:
        raise HTTPException(404, "任务不存在")
    if c.status != "draft":
        raise HTTPException(409, f"当前状态 {c.status} 不能启动预跑")
    if not c.icp.get("industry_keywords"):
        raise HTTPException(422, "ICP 缺少行业关键词")
    c.status = "dry_run"
    audit.record(db, current.tenant_id, "campaign", c.id, "campaign.dry_run_started", {})
    db.commit()
    # 入队一轮发现（worker 侧执行）
    from app.modules.discovery.tasks import run_campaign
    run_campaign.delay(str(c.id))
    return _out(c)


class LeadOut(BaseModel):
    id: str
    company_name: str
    domain: str
    country: str
    score: int
    score_reason: str
    status: str


@router.get("/{campaign_id}/leads", response_model=list[LeadOut])
def list_leads(campaign_id: uuid.UUID, current: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_tenant_db)) -> list[LeadOut]:
    rows = db.execute(
        select(Lead, Company).join(Company, Lead.company_id == Company.id)
        .where(Lead.tenant_id == current.tenant_id, Lead.campaign_id == campaign_id)
        .order_by(Lead.score.desc())
    ).all()
    return [LeadOut(id=str(lead.id), company_name=co.name, domain=co.domain, country=co.country,
                    score=lead.score, score_reason=lead.score_reason, status=lead.status)
            for lead, co in rows]
