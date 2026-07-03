"""两级 LLM 研判（架构 §5.1 research 阶段 + §5.2 成本闸门）。

cheap 初筛：是否目标行业/B2B（≥60 分才进精评）
strong 精评：0-100 匹配度 + 一句话理由 + 事实清单（每条必须带来源 URL —— ADR-7）
"""
from dataclasses import dataclass, field

from app.modules.ai_gateway.gateway import invoke_json

SCREEN_THRESHOLD = 60

_SCREEN_SYSTEM = """你是外贸线索初筛员。根据公司网站文本判断该公司是否可能是给定 ICP 的目标客户。
输出 JSON: {"screen_score": 0-100, "is_b2b": bool, "reason": "一句话"}"""

_RESEARCH_SYSTEM = """你是外贸客户研究员。根据公司网站文本，评估其与 ICP 的匹配度并提取事实。
规则：
- facts 中每条必须注明来源 URL（只能用文本中出现的 [url] 标记），无法溯源的信息不要写；
- 不要推测未出现的信息；
- reason 用一句中文概括为什么匹配/不匹配。
输出 JSON: {"score": 0-100, "reason": "…",
 "facts": [{"text": "英文事实原文或忠实转述", "source_url": "…"}],
 "contacts_hint": [{"name": "…", "title": "…"}]}"""


@dataclass
class ResearchOutcome:
    score: int = 0
    reason: str = ""
    facts: list[dict] = field(default_factory=list)      # {text, source_url}
    contacts_hint: list[dict] = field(default_factory=list)
    screened_out: bool = False


def _icp_brief(icp: dict) -> str:
    return (f"目标国家: {icp.get('countries')}\n行业关键词: {icp.get('industry_keywords')}\n"
            f"公司类型: {icp.get('company_types')}\n补充要求: {icp.get('freeform', '无')}")


def research_company(icp: dict, site_text: str, byok_api_key: str | None = None) -> ResearchOutcome:
    screen = invoke_json(
        "screen_company", _SCREEN_SYSTEM,
        f"ICP:\n{_icp_brief(icp)}\n\n网站文本:\n{site_text[:6000]}",
        byok_api_key=byok_api_key, max_tokens=200,
    )
    if int(screen.get("screen_score", 0)) < SCREEN_THRESHOLD:
        return ResearchOutcome(score=int(screen.get("screen_score", 0)),
                               reason=str(screen.get("reason", "")), screened_out=True)

    detail = invoke_json(
        "research_company", _RESEARCH_SYSTEM,
        f"ICP:\n{_icp_brief(icp)}\n\n网站文本:\n{site_text[:24000]}",
        byok_api_key=byok_api_key, max_tokens=1500,
    )
    # 反幻觉数据层校验：无 source_url 的事实直接丢弃（ADR-7）
    facts = [f for f in detail.get("facts", [])
             if isinstance(f, dict) and f.get("source_url") and f.get("text")]
    return ResearchOutcome(
        score=max(0, min(100, int(detail.get("score", 0)))),
        reason=str(detail.get("reason", "")),
        facts=facts,
        contacts_hint=detail.get("contacts_hint", []) or [],
    )
