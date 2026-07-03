"""discovery 流水线端到端集成测试（外部依赖全 mock，验证编排与状态流转）。"""
import uuid
from unittest.mock import patch

from app.modules.campaign.models import Campaign
from app.modules.contact.models import Contact, EmailCandidate
from app.modules.contact.verifier import VerifyResult
from app.modules.discovery.adapters.base import CompanyCandidate, DataSourceAdapter
from app.modules.discovery.crawler import CrawlResult
from app.modules.discovery.models import Company, Lead, ResearchFact
from app.modules.discovery.pipeline import run_campaign_discovery
from app.modules.discovery.scoring import ResearchOutcome


class FakeAdapter(DataSourceAdapter):
    name = "fake"

    def available(self) -> bool:
        return True

    def discover(self, icp, limit=50):
        return [
            CompanyCandidate(domain="harborhale.com", name="Harbor & Hale Lighting",
                             country="US", source="fake"),
            CompanyCandidate(domain="harborhale.com", name="重复域名应去重", country="US"),
            CompanyCandidate(domain="badfit.com", name="Bad Fit Inc", country="US"),
        ]


GOOD = ResearchOutcome(score=91, reason="照明分销商，高度匹配",
                       facts=[{"text": "Opened new showroom in Bend",
                               "source_url": "https://harborhale.com/news"}],
                       contacts_hint=[{"name": "Megan Cho", "title": "Co-founder"}])
BAD = ResearchOutcome(score=20, reason="非目标行业", screened_out=True)


def _mk_campaign(db) -> Campaign:
    c = Campaign(tenant_id=uuid.uuid4(), owner_user_id=uuid.uuid4(), name="t",
                 status="dry_run", icp={"countries": ["US"], "industry_keywords": ["led"]})
    db.add(c)
    db.commit()
    return c


@patch("app.modules.contact.service.verify_email",
       return_value=VerifyResult(status="valid", confidence="high"))
@patch("app.modules.discovery.pipeline.research_company",
       side_effect=lambda icp, text: GOOD if "harborhale" in text else BAD)
@patch("app.modules.discovery.pipeline.crawl_site",
       side_effect=lambda d: CrawlResult(domain=d, pages={f"https://{d}/": f"site of {d}"}))
@patch("app.modules.discovery.pipeline.ADAPTERS", [FakeAdapter()])
def test_full_pipeline(mock_crawl, mock_research, mock_verify, db):
    campaign = _mk_campaign(db)
    stats = run_campaign_discovery(db, campaign.id)

    # 去重：3 个候选 → 2 家公司
    assert db.query(Company).count() == 2
    assert stats["new_companies"] == 2

    leads = {db.get(Company, l.company_id).domain: l for l in db.query(Lead).all()}
    # 匹配的 → ready（有 high 置信度邮箱）；不匹配的 → excluded
    assert leads["harborhale.com"].status == "ready"
    assert leads["harborhale.com"].score == 91
    assert leads["badfit.com"].status == "excluded"

    # 事实带出处入缓存；联系人与邮箱候选落库
    assert db.query(ResearchFact).filter_by(domain="harborhale.com").count() == 1
    contact = db.query(Contact).filter_by(full_name="Megan Cho").one()
    email = db.query(EmailCandidate).filter_by(contact_id=contact.id).first()
    assert email.email == "megan.cho@harborhale.com"
    assert email.confidence == "high"


@patch("app.modules.contact.service.verify_email",
       return_value=VerifyResult(status="unverified", confidence="low"))
@patch("app.modules.discovery.pipeline.research_company", return_value=GOOD)
@patch("app.modules.discovery.pipeline.crawl_site",
       side_effect=lambda d: CrawlResult(domain=d, pages={f"https://{d}/": "x"}))
@patch("app.modules.discovery.pipeline.ADAPTERS", [FakeAdapter()])
def test_no_sendable_email_marks_incomplete(mock_crawl, mock_research, mock_verify, db):
    campaign = _mk_campaign(db)
    run_campaign_discovery(db, campaign.id)
    lead = db.query(Lead).join(Company, Lead.company_id == Company.id).filter(
        Company.domain == "harborhale.com").one()
    assert lead.status == "incomplete"  # low 置信度不进发送队列（FR-CNT-02）
