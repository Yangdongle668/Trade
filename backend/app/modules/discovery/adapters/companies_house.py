"""UK Companies House API：官方、完全免费（04 文档 §2.1 的"宝藏源"）。

返回公司注册信息 + SIC 行业码；董事名单可作决策人线索（contact 模块消费）。
"""
import httpx
import structlog

from app.core.config import get_settings
from app.modules.discovery.adapters.base import CompanyCandidate, DataSourceAdapter

log = structlog.get_logger()


class CompaniesHouseAdapter(DataSourceAdapter):
    name = "companies_house"

    def available(self) -> bool:
        return bool(get_settings().companies_house_api_key)

    def discover(self, icp: dict, limit: int = 50) -> list[CompanyCandidate]:
        if "GB" not in icp.get("countries", []):
            return []
        s = get_settings()
        out: list[CompanyCandidate] = []
        for kw in icp.get("industry_keywords", [])[:5]:
            if len(out) >= limit:
                break
            try:
                resp = httpx.get(
                    "https://api.company-information.service.gov.uk/search/companies",
                    params={"q": kw, "items_per_page": 20},
                    auth=(s.companies_house_api_key, ""),
                    timeout=20,
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("ch.error", kw=kw, error=str(e))
                continue
            for item in resp.json().get("items", []):
                if item.get("company_status") != "active":
                    continue
                # CH 无官网字段：domain 留空，交给流水线 crawl 阶段按公司名搜索补全
                out.append(CompanyCandidate(
                    domain="",
                    name=item.get("title", "")[:255],
                    country="GB",
                    source=self.name,
                    meta={
                        "company_number": item.get("company_number"),
                        "address": (item.get("address_snippet") or ""),
                        "sic_codes": item.get("sic_codes", []),
                    },
                ))
        return out
