"""投递窗口计算（不变量 4）：收件人当地工作日 08:30–11:30 内随机时点。"""
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WINDOW_START = (8, 30)
WINDOW_END = (11, 30)

# 联系人无精确时区时按国家默认（03 文档遗留问题 2：v0 国家级）
COUNTRY_DEFAULT_TZ = {
    "US": "America/Chicago", "GB": "Europe/London", "CA": "America/Toronto",
    "AU": "Australia/Sydney", "NZ": "Pacific/Auckland",
}


def resolve_timezone(contact_tz: str, country: str) -> str:
    if contact_tz:
        try:
            ZoneInfo(contact_tz)
            return contact_tz
        except Exception:
            pass
    return COUNTRY_DEFAULT_TZ.get(country, "UTC")


def next_send_time(tz_name: str, after_utc: datetime, rng: random.Random | None = None) -> datetime:
    """返回 after_utc 之后最近的一个「当地工作日窗口内随机时点」（UTC）。"""
    rng = rng or random.Random()
    tz = ZoneInfo(tz_name)
    local = after_utc.astimezone(tz)

    for _ in range(10):  # 最多前探 10 天（跨周末足够）
        start = local.replace(hour=WINDOW_START[0], minute=WINDOW_START[1],
                              second=0, microsecond=0)
        end = local.replace(hour=WINDOW_END[0], minute=WINDOW_END[1],
                            second=0, microsecond=0)
        if local.weekday() < 5 and local < end:
            earliest = max(local, start)
            span = int((end - earliest).total_seconds())
            offset = rng.randint(0, max(span, 1))
            return (earliest + timedelta(seconds=offset)).astimezone(timezone.utc)
        local = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    raise RuntimeError("窗口计算失败")  # 不可达
