"""Google Places API（New）：品类 × 城市网格扫描（03 文档 S2）。

免费月度额度内使用；评论数/评分作为规模与活跃度信号进 meta。
"""
import httpx
import structlog

from app.common.domain import normalize_domain
from app.core.config import get_settings
from app.modules.discovery.adapters.base import CompanyCandidate, DataSourceAdapter

log = structlog.get_logger()

# v0 起步城市表（英语区 Top 城市，M1 后期扩到配置化城市网格）
SEED_CITIES = {
    "US": ["New York", "Los Angeles", "Chicago", "Houston", "Dallas", "Atlanta"],
    "GB": ["London", "Manchester", "Birmingham", "Leeds"],
    "CA": ["Toronto", "Vancouver", "Montreal"],
    "AU": ["Sydney", "Melbourne", "Brisbane"],
    "NZ": ["Auckland"],
}


class GoogleMapsAdapter(DataSourceAdapter):
    name = "maps"

    def available(self) -> bool:
        return bool(get_settings().google_maps_api_key)

    def discover(self, icp: dict, limit: int = 50) -> list[CompanyCandidate]:
        s = get_settings()
        out: dict[str, CompanyCandidate] = {}
        kws = icp.get("industry_keywords", [])[:3]
        for country in icp.get("countries", ["US"]):
            for city in SEED_CITIES.get(country, [])[:4]:
                for kw in kws:
                    if len(out) >= limit:
                        return list(out.values())
                    try:
                        resp = httpx.post(
                            "https://places.googleapis.com/v1/places:searchText",
                            headers={
                                "X-Goog-Api-Key": s.google_maps_api_key,
                                "X-Goog-FieldMask": "places.displayName,places.websiteUri,"
                                                    "places.rating,places.userRatingCount,"
                                                    "places.formattedAddress",
                            },
                            json={"textQuery": f"{kw} distributor in {city}", "pageSize": 10},
                            timeout=20,
                        )
                        resp.raise_for_status()
                    except httpx.HTTPError as e:
                        log.warning("maps.error", city=city, kw=kw, error=str(e))
                        continue
                    for p in resp.json().get("places", []):
                        domain = normalize_domain(p.get("websiteUri", ""))
                        if not domain or domain in out:
                            continue  # 无官网条目降权直接跳过（03 文档 S2）
                        out[domain] = CompanyCandidate(
                            domain=domain,
                            name=p.get("displayName", {}).get("text", "")[:255],
                            country=country,
                            city=city,
                            website=p.get("websiteUri", ""),
                            source=self.name,
                            meta={
                                "rating": p.get("rating"),
                                "review_count": p.get("userRatingCount"),
                                "address": p.get("formattedAddress", ""),
                            },
                        )
        return list(out.values())
