"""自托管 Reacher SMTP 验证客户端（04 文档 §2.2）。

铁律（FR-CNT-02）：置信度非 high/medium 的邮箱绝不进发送队列。
Reacher 未部署（URL 未配）时全部降级为 unverified/low —— 宁保守勿冒险。
"""
from dataclasses import dataclass

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()

# Reacher is_reachable → (verify_status, confidence)
_REACHER_MAP = {
    "safe": ("valid", "high"),
    "risky": ("catch_all", "medium"),   # catch-all 域：可发但降级
    "invalid": ("invalid", "invalid"),
    "unknown": ("unknown", "low"),
}


@dataclass
class VerifyResult:
    status: str       # valid | catch_all | invalid | unknown | unverified
    confidence: str   # high | medium | low | invalid


def verify_email(email: str) -> VerifyResult:
    base = get_settings().reacher_base_url
    if not base:
        return VerifyResult(status="unverified", confidence="low")
    try:
        resp = httpx.post(f"{base.rstrip('/')}/v0/check_email",
                          json={"to_email": email}, timeout=45)
        resp.raise_for_status()
        reachable = resp.json().get("is_reachable", "unknown")
    except httpx.HTTPError as e:
        log.warning("verify.error", email=email, error=str(e))
        return VerifyResult(status="unverified", confidence="low")
    status, confidence = _REACHER_MAP.get(reachable, ("unknown", "low"))
    return VerifyResult(status=status, confidence=confidence)
