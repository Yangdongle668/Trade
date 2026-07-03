"""Google Programmable Search：免费 100 次/天（04 文档 §2.1）。

操作点（03 文档 S3）：AI 生成的搜索式 → PSE 取回候选 URL → 归一化域名。
"""
import httpx
import structlog

from app.common.domain import normalize_domain
from app.core.config import get_settings
from app.modules.discovery.adapters.base import CompanyCandidate, DataSourceAdapter

log = structlog.get_logger()

# 英语区目标国的 ccTLD 与 gl 参数
COUNTRY_GL = {"US": "us", "GB": "uk", "CA": "ca", "AU": "au", "NZ": "nz"}


def build_queries(icp: dict) -> list[str]:
    """v0 用模板生成搜索式；M1 后期切换为 AI 生成+按产出淘汰（架构 §5.1 icp.compile）。"""
    kws = icp.get("industry_keywords", [])
    types = icp.get("company_types", ["distributor", "wholesaler", "importer"])
    queries = []
    for kw in kws[:5]:
        for t in types[:3]:
            queries.append(f'"{kw}" {t}')
    return queries


class GooglePSEAdapter(DataSourceAdapter):
    name = "pse"

    def available(self) -> bool:
        s = get_settings()
        return bool(s.google_pse_api_key and s.google_pse_cx)

    def discover(self, icp: dict, limit: int = 50) -> list[CompanyCandidate]:
        s = get_settings()
        out: dict[str, CompanyCandidate] = {}
        countries = icp.get("countries", ["US"])
        for query in build_queries(icp):
            for country in countries:
                if len(out) >= limit:
                    return list(out.values())
                try:
                    resp = httpx.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params={"key": s.google_pse_api_key, "cx": s.google_pse_cx,
                                "q": query, "gl": COUNTRY_GL.get(country, "us"), "num": 10},
                        timeout=20,
                    )
                    resp.raise_for_status()
                except httpx.HTTPError as e:
                    log.warning("pse.error", query=query, error=str(e))
                    continue
                for item in resp.json().get("items", []):
                    domain = normalize_domain(item.get("link", ""))
                    if domain and domain not in out:
                        out[domain] = CompanyCandidate(
                            domain=domain,
                            name=item.get("title", "")[:255],
                            country=country,
                            website=item.get("link", ""),
                            source=self.name,
                            meta={"query": query, "snippet": item.get("snippet", "")},
                        )
        return list(out.values())
