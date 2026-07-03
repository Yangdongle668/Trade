"""域名归一化 —— 租户内线索去重与撞单保护的基石（架构 §4.2）。

规则：companies.domain 唯一键 = eTLD+1（注册域），
子域名（shop.example.co.uk）归并到注册域（example.co.uk）。
"""
from urllib.parse import urlparse

import tldextract

# 禁网提取（不在线更新公共后缀表，用内置快照，保证 worker 离线可用）
_extract = tldextract.TLDExtract(suffix_list_urls=())

# 平台域名不是"公司"，出现即丢弃（线索质量护栏）
PLATFORM_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "youtube.com", "amazon.com", "ebay.com", "alibaba.com", "aliexpress.com",
    "etsy.com", "pinterest.com", "yelp.com", "wikipedia.org", "google.com",
}


def normalize_domain(url_or_domain: str) -> str | None:
    """任意 URL / 域名 → 注册域小写；无效或平台域返回 None。"""
    raw = url_or_domain.strip().lower()
    if not raw:
        return None
    if "//" not in raw:
        raw = "//" + raw
    host = urlparse(raw, scheme="http").hostname or ""
    ext = _extract(host)
    if not ext.domain or not ext.suffix:
        return None
    domain = f"{ext.domain}.{ext.suffix}"
    if domain in PLATFORM_DOMAINS:
        return None
    return domain
