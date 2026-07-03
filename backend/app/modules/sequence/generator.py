"""开发信生成（FR-GEN-01/03）：事实只来自 BrandKit + ResearchFact。

反幻觉闸门（ADR-7）：产出中的具体数字/认证/URL 逐一回查来源文本，
匹配不上 → 拒绝该稿（调用方重试或降级为通用稿）。
"""
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai_gateway.gateway import invoke_json
from app.modules.ai_gateway.guardrails import check_email_body
from app.modules.brandkit.models import BrandAsset
from app.modules.discovery.models import Company, ResearchFact

_SYSTEM = """You write concise, personalized B2B cold-outreach emails for a Chinese exporter
selling to English-speaking markets. Rules:
- Open with ONE specific fact about the prospect taken ONLY from the provided research facts.
- Product claims (MOQ, certifications, lead time, numbers) may ONLY come from the brand assets.
- Plain text, under 150 words, exactly one soft call-to-action, no links unless given, no emoji.
- Write at a native business-English level. Sign with the sender name given.
Angle for this step: {angle}.
输出 JSON: {{"subject": "…", "body": "…"}}"""

ANGLES = {
    "intro": "first touch — introduce the fit between their business and our product",
    "case": "follow-up — share a relevant customer result or reorder story from brand assets",
    "insight": "follow-up — a useful industry observation, low pressure",
    "breakup": "polite final note — leave the door open, no pressure",
}


@dataclass
class DraftResult:
    ok: bool
    subject: str = ""
    body: str = ""
    used_fact_urls: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


def generate_email(db: Session, tenant_id, company: Company, angle: str,
                   sender_name: str, byok_api_key: str | None = None) -> DraftResult:
    facts = db.execute(
        select(ResearchFact).where(ResearchFact.domain == company.domain).limit(8)
    ).scalars().all()
    assets = db.execute(
        select(BrandAsset).where(BrandAsset.tenant_id == tenant_id,
                                 BrandAsset.ai_quotable.is_(True)).limit(10)
    ).scalars().all()

    facts_txt = "\n".join(f"- {f.fact_text} (source: {f.source_url})" for f in facts) or "- (none)"
    assets_txt = "\n".join(
        f"- [{a.kind}] {a.title}: " + "; ".join(f"{k}={v}" for k, v in a.content.items())
        for a in assets) or "- (none)"

    out = invoke_json(
        "draft_email",
        _SYSTEM.format(angle=ANGLES.get(angle, ANGLES["intro"])),
        f"Prospect company: {company.name} ({company.domain}, {company.country})\n"
        f"Research facts about the prospect:\n{facts_txt}\n\n"
        f"Our brand assets (the ONLY allowed source for product claims):\n{assets_txt}\n\n"
        f"Sender name: {sender_name}",
        byok_api_key=byok_api_key, max_tokens=600,
    )
    subject, body = str(out.get("subject", "")).strip(), str(out.get("body", "")).strip()

    violations = _fact_check(subject + "\n" + body, facts_txt + "\n" + assets_txt)
    guard = check_email_body(subject, body)
    violations += guard.violations
    if violations:
        return DraftResult(ok=False, subject=subject, body=body, violations=violations)
    return DraftResult(ok=True, subject=subject, body=body,
                       used_fact_urls=[f.source_url for f in facts])


_NUM_RE = re.compile(r"\b\d[\d,.]*\s*(?:%|w|kw|units?|days?|pcs|years?)?\b", re.I)
_CERT_RE = re.compile(r"\b(ETL|UL|CE|FCC|RoHS|ISO ?\d*|DLC|SAA)\b", re.I)


def _fact_check(draft: str, sources: str) -> list[str]:
    """具体声明必须能在来源文本中找到：数字（含单位）与认证名逐一回查。"""
    violations = []
    src = sources.lower()
    for m in _CERT_RE.finditer(draft):
        # 词边界匹配，避免 "CE" 误命中 "cert" 之类子串
        if not re.search(rf"\b{re.escape(m.group(0))}\b", sources, re.I):
            violations.append(f"认证「{m.group(0)}」无来源")
    for m in _NUM_RE.finditer(draft):
        token = m.group(0).strip().lower()
        if len(token) <= 1:  # 单个数字（如序号）不查
            continue
        if token.replace(",", "") not in src.replace(",", ""):
            violations.append(f"数字「{m.group(0).strip()}」无来源")
    return violations
