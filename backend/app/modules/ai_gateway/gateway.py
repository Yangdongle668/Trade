"""AI 网关（架构 §8）：模型分级路由 + BYOK/平台双模式 + 用量计量。

调用方永远经 invoke() 进入，不直连供应商 SDK——
提示词版本、反幻觉闸门、计量都在这一层集中实施。
"""
import json
import uuid
from dataclasses import dataclass

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()

# task → 档位（cheap: 初筛/分类/抽取；strong: 精评/写信/回复草拟）
TASK_TIER = {
    "screen_company": "cheap",
    "classify_reply": "cheap",
    "extract_contacts": "cheap",
    "research_company": "strong",
    "draft_email": "strong",
    "draft_reply": "strong",
}


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class AIGatewayError(Exception):
    pass


def invoke(task: str, system: str, user_content: str,
           byok_api_key: str | None = None, max_tokens: int = 1024) -> LLMResult:
    """同步调用（worker 内使用）。byok_api_key 传入则计入用户账单（BYOK 模式）。"""
    s = get_settings()
    tier = TASK_TIER.get(task, "cheap")
    model = s.llm_strong_model if tier == "strong" else s.llm_cheap_model
    api_key = byok_api_key or s.anthropic_api_key
    if not api_key:
        raise AIGatewayError("无可用 LLM Key：请在设置中配置 BYOK，或联系平台")

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        json={
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise AIGatewayError(f"LLM 调用失败 {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []))
    usage = data.get("usage", {})
    result = LLMResult(
        text=text,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        model=model,
    )
    log.info("llm.call", task=task, model=model,
             tokens_in=result.input_tokens, tokens_out=result.output_tokens,
             byok=bool(byok_api_key))
    return result


def invoke_json(task: str, system: str, user_content: str, **kw) -> dict:
    """要求模型输出 JSON 并解析；解析失败抛错（调用方决定重试或降级）。"""
    res = invoke(task, system + "\n\n只输出一个合法 JSON 对象，不要任何其他文字。", user_content, **kw)
    text = res.text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIGatewayError(f"LLM 未返回合法 JSON: {text[:200]}") from e
