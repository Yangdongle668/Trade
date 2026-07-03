import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.quota.models import FREE_PLAN_LIMITS, UsageCounter


class QuotaExceeded(Exception):
    pass


def _period(metric: str) -> str:
    now = datetime.now(timezone.utc)
    # 数据源免费额度与发送量按日记账（架构 §5.2/§6.3），业务配额按月
    daily = metric.endswith("_queries") or metric.startswith("send:")
    return now.strftime("%Y-%m-%d") if daily else now.strftime("%Y-%m")


def check_and_increment(db: Session, tenant_id: uuid.UUID, metric: str, amount: int = 1,
                        limit: int | None = None, period: str | None = None) -> None:
    limit = limit if limit is not None else FREE_PLAN_LIMITS.get(metric)
    period = period or _period(metric)
    row = db.execute(
        select(UsageCounter).where(
            UsageCounter.tenant_id == tenant_id,
            UsageCounter.metric == metric,
            UsageCounter.period == period,
        ).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        row = UsageCounter(tenant_id=tenant_id, metric=metric, period=period, used=0)
        db.add(row)
        db.flush()
    if limit is not None and row.used + amount > limit:
        raise QuotaExceeded(f"{metric} 配额已用尽（{row.used}/{limit}）")
    row.used += amount
