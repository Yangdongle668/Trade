"""线索发现流水线编排（架构 §5.1）：
icp → source.fetch（各适配器）→ dedupe（域名唯一键）→ crawl → research → lead 落库。

v0 简化：单 Campaign 的一轮批处理在一个任务内串行完成（量小），
M2 拆为逐阶段队列任务。
"""
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.campaign.models import Campaign
from app.modules.discovery.adapters.base import DataSourceAdapter
from app.modules.discovery.adapters.companies_house import CompaniesHouseAdapter
from app.modules.discovery.adapters.google_maps import GoogleMapsAdapter
from app.modules.discovery.adapters.google_pse import GooglePSEAdapter
from app.modules.discovery.crawler import crawl_site
from app.modules.discovery.models import Company, Lead, ResearchFact, SourceRun
from app.modules.discovery.scoring import research_company
from app.modules.quota.service import QuotaExceeded, check_and_increment

log = structlog.get_logger()

ADAPTERS: list[DataSourceAdapter] = [GooglePSEAdapter(), GoogleMapsAdapter(), CompaniesHouseAdapter()]
RESEARCH_CACHE_DAYS = 90
BATCH_LIMIT_PER_RUN = 60  # 免费版单轮上限，兼顾配额与夜间时长


def run_campaign_discovery(db: Session, campaign_id: uuid.UUID) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.status not in ("dry_run", "active"):
        return {"skipped": True}
    tenant_id, icp = campaign.tenant_id, campaign.icp
    stats = {"candidates": 0, "new_companies": 0, "scored": 0, "ready": 0}

    for adapter in ADAPTERS:
        if not adapter.available():
            continue
        run = SourceRun(tenant_id=tenant_id, campaign_id=campaign_id, adapter=adapter.name)
        db.add(run)
        db.flush()
        try:
            candidates = adapter.discover(icp, limit=BATCH_LIMIT_PER_RUN)
        except Exception as e:  # 单源故障不影响其余源（架构 §5.2 熔断从简：记账+跳过）
            run.status, run.detail = "failed", {"error": str(e)[:500]}
            log.warning("discovery.adapter_failed", adapter=adapter.name, error=str(e))
            continue
        run.status, run.candidates_found = "done", len(candidates)
        stats["candidates"] += len(candidates)

        for cand in candidates:
            if not cand.domain:
                continue  # CH 等无域名候选：M1 后期补"按公司名搜官网"回填
            company = db.execute(
                select(Company).where(Company.tenant_id == tenant_id,
                                      Company.domain == cand.domain)
            ).scalar_one_or_none()
            if company is None:
                company = Company(tenant_id=tenant_id, domain=cand.domain, name=cand.name,
                                  country=cand.country, city=cand.city,
                                  source=cand.source, meta=cand.meta)
                db.add(company)
                db.flush()
                stats["new_companies"] += 1
            # 租户内同 Campaign 去重
            exists = db.execute(
                select(Lead.id).where(Lead.tenant_id == tenant_id,
                                      Lead.company_id == company.id,
                                      Lead.campaign_id == campaign_id)
            ).first()
            if exists:
                continue
            db.add(Lead(tenant_id=tenant_id, company_id=company.id, campaign_id=campaign_id,
                        owner_user_id=campaign.owner_user_id))
        db.commit()

    # 研判阶段：处理本 Campaign 所有 discovered 线索
    leads = db.execute(
        select(Lead).where(Lead.tenant_id == tenant_id, Lead.campaign_id == campaign_id,
                           Lead.status == "discovered").limit(BATCH_LIMIT_PER_RUN)
    ).scalars().all()
    for lead in leads:
        try:
            check_and_increment(db, tenant_id, "leads_per_month")
        except QuotaExceeded:
            log.info("discovery.quota_exhausted", tenant=str(tenant_id))
            break
        company = db.get(Company, lead.company_id)
        outcome = _research_with_cache(db, icp, company)
        lead.score, lead.score_reason = outcome.score, outcome.reason
        lead.status = "excluded" if outcome.screened_out else "scored"
        if not outcome.screened_out:
            stats["scored"] += 1
        audit.record(db, tenant_id, "lead", lead.id, "lead.scored",
                     {"score": lead.score, "reason": lead.score_reason})
        db.commit()
    return stats


def _research_with_cache(db: Session, icp: dict, company: Company):
    """域名级 90 天研判缓存：公开事实跨租户共享（架构 §5.2）。"""
    from app.modules.discovery.scoring import ResearchOutcome

    now = datetime.now(timezone.utc)
    cached = db.execute(
        select(ResearchFact).where(ResearchFact.domain == company.domain,
                                   ResearchFact.expires_at > now)
    ).scalars().all()
    if cached:
        site_text = "\n".join(f"[{f.source_url}]\n{f.fact_text}" for f in cached)
    else:
        crawl = crawl_site(company.domain)
        if not crawl.pages:
            return ResearchOutcome(score=0, reason=f"官网不可达（{crawl.error}）", screened_out=True)
        site_text = crawl.combined_text

    outcome = research_company(icp, site_text)
    if not cached:
        for fact in outcome.facts:
            db.add(ResearchFact(domain=company.domain, fact_text=fact["text"],
                                source_url=fact["source_url"],
                                expires_at=now + timedelta(days=RESEARCH_CACHE_DAYS)))
    return outcome
