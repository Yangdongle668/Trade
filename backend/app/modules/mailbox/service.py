"""发信身份健康与日限（架构 §6.3）：
warming(21 天爬坡) → healthy → throttled(退信>3% 减半) → paused(投诉熔断)。
日发送计数走 usage_counters（metric=send:{mailbox_id}，按日 period）。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit import service as audit
from app.modules.mailbox.models import Mailbox
from app.modules.quota.models import UsageCounter

WARMUP_DAYS = 21
# 预热爬坡表：天数 → 日限
WARMUP_RAMP = [(0, 5), (7, 10), (14, 15), (21, 0)]  # 第 21 天转 healthy


def effective_daily_limit(mailbox: Mailbox) -> int:
    s = get_settings()
    if mailbox.health == "paused":
        return 0
    if mailbox.health == "throttled":
        return max(1, s.send_daily_limit_healthy // 2)
    if mailbox.health == "warming":
        limit = s.send_daily_limit_warming
        for day, ramp in WARMUP_RAMP:
            if mailbox.warmup_day >= day and ramp:
                limit = ramp
        return limit
    return min(mailbox.daily_limit or s.send_daily_limit_healthy, s.send_daily_limit_healthy)


def _today_metric(mailbox_id: uuid.UUID) -> tuple[str, str]:
    return f"send:{mailbox_id}", datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sends_today(db: Session, tenant_id: uuid.UUID, mailbox_id: uuid.UUID) -> int:
    metric, period = _today_metric(mailbox_id)
    used = db.execute(
        select(func.coalesce(func.sum(UsageCounter.used), 0)).where(
            UsageCounter.tenant_id == tenant_id, UsageCounter.metric == metric,
            UsageCounter.period == period)
    ).scalar_one()
    return int(used)


def can_send(db: Session, mailbox: Mailbox) -> tuple[bool, str]:
    if mailbox.health == "paused":
        return False, "发信身份已熔断，需人工诊断恢复"
    limit = effective_daily_limit(mailbox)
    used = sends_today(db, mailbox.tenant_id, mailbox.id)
    if used >= limit:
        return False, f"今日限额已用（{used}/{limit}）"
    return True, ""


def record_send(db: Session, mailbox: Mailbox) -> None:
    from app.modules.quota.service import check_and_increment
    metric, _ = _today_metric(mailbox.id)
    check_and_increment(db, mailbox.tenant_id, metric, limit=None)


def record_hard_bounce(db: Session, mailbox: Mailbox) -> None:
    """硬退信：计数并按阈值降速/熔断（v0 简化：单日退信 ≥2 次即降速）。"""
    from app.modules.quota.service import check_and_increment
    metric = f"bounce:{mailbox.id}"
    check_and_increment(db, mailbox.tenant_id, metric, limit=None)
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    bounces = db.execute(
        select(func.coalesce(func.sum(UsageCounter.used), 0)).where(
            UsageCounter.tenant_id == mailbox.tenant_id,
            UsageCounter.metric == metric, UsageCounter.period == period)
    ).scalar_one()
    if bounces >= 2 and mailbox.health in ("healthy", "warming"):
        mailbox.health = "throttled"
        audit.record(db, mailbox.tenant_id, "mailbox", mailbox.id,
                     "mailbox.throttled", {"bounces_this_month": int(bounces)})


def advance_warmup(db: Session) -> int:
    """每日推进预热天数；满 21 天转 healthy。由 maintenance-daily 调用。"""
    rows = db.execute(select(Mailbox).where(Mailbox.health == "warming")).scalars().all()
    for mb in rows:
        mb.warmup_day += 1
        if mb.warmup_day >= WARMUP_DAYS:
            mb.health = "healthy"
            mb.daily_limit = get_settings().send_daily_limit_healthy
            audit.record(db, mb.tenant_id, "mailbox", mb.id, "mailbox.warmup_completed", {})
    return len(rows)
