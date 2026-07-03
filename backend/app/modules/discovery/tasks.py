import structlog
from sqlalchemy import select

from app.celery_app import celery
from app.core.db import SessionLocal
from app.modules.campaign.models import Campaign
from app.modules.discovery.pipeline import run_campaign_discovery

log = structlog.get_logger()


@celery.task(name="app.modules.discovery.tasks.run_campaign", bind=True, max_retries=2)
def run_campaign(self, campaign_id: str) -> dict:
    with SessionLocal() as db:
        stats = run_campaign_discovery(db, campaign_id)
        log.info("discovery.run_done", campaign=campaign_id, **{k: v for k, v in stats.items()})
        return stats


@celery.task(name="app.modules.discovery.tasks.run_due_campaigns")
def run_due_campaigns() -> int:
    """夜间批：所有 active/dry_run Campaign 逐个入队（错峰由队列并发度控制）。"""
    with SessionLocal() as db:
        ids = db.execute(
            select(Campaign.id).where(Campaign.status.in_(["active", "dry_run"]))
        ).scalars().all()
    for cid in ids:
        run_campaign.delay(str(cid))
    return len(ids)
