"""官网爬读：HTTP 直取优先，正文抽取供 LLM 研判（架构 §5.1 crawl 阶段）。

v0 不做 JS 渲染（Playwright 兜底在 M1 后期加）；robots 遵从 + 限速。
"""
import urllib.robotparser
from dataclasses import dataclass, field

import httpx
import structlog
from bs4 import BeautifulSoup

log = structlog.get_logger()

UA = "OutreachCopilotBot/0.1 (+https://example.com/bot; research for B2B matching)"
KEY_PATHS = ["/", "/about", "/about-us", "/products", "/services", "/contact", "/news"]
MAX_CHARS_PER_PAGE = 8000


@dataclass
class CrawlResult:
    domain: str
    pages: dict[str, str] = field(default_factory=dict)  # url → 正文文本
    error: str = ""

    @property
    def combined_text(self) -> str:
        return "\n\n".join(f"[{u}]\n{t}" for u, t in self.pages.items())


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:MAX_CHARS_PER_PAGE]


def crawl_site(domain: str) -> CrawlResult:
    result = CrawlResult(domain=domain)
    base = f"https://{domain}"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(f"{base}/robots.txt")
        rp.read()
    except Exception:
        rp = None  # robots 不可达时按可抓处理，但保持限速

    with httpx.Client(headers={"User-Agent": UA}, timeout=15, follow_redirects=True) as client:
        for path in KEY_PATHS:
            url = base + path
            if rp is not None and not rp.can_fetch(UA, url):
                continue
            try:
                resp = client.get(url)
                if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                    text = _extract_text(resp.text)
                    if len(text) > 100:
                        result.pages[url] = text
            except httpx.HTTPError as e:
                if path == "/":
                    result.error = str(e)
    if not result.pages and not result.error:
        result.error = "no_content"
    return result
