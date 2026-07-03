import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.modules.sequence.windows import next_send_time, resolve_timezone


def test_weekday_morning_inside_window():
    # 周一 12:00 UTC = 芝加哥周一 06:00 → 当天窗口 08:30–11:30
    after = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    t = next_send_time("America/Chicago", after, random.Random(42))
    local = t.astimezone(ZoneInfo("America/Chicago"))
    assert local.weekday() == 0
    assert (8, 30) <= (local.hour, local.minute) <= (11, 30)


def test_after_window_rolls_to_next_day():
    # 芝加哥周一 15:00（窗口已过）→ 周二
    after = datetime(2026, 7, 6, 20, 0, tzinfo=timezone.utc)
    local = next_send_time("America/Chicago", after).astimezone(ZoneInfo("America/Chicago"))
    assert local.weekday() == 1


def test_weekend_rolls_to_monday():
    # 伦敦周六 → 周一
    after = datetime(2026, 7, 4, 6, 0, tzinfo=timezone.utc)
    local = next_send_time("Europe/London", after).astimezone(ZoneInfo("Europe/London"))
    assert local.weekday() == 0


def test_resolve_timezone_fallbacks():
    assert resolve_timezone("", "GB") == "Europe/London"
    assert resolve_timezone("America/New_York", "GB") == "America/New_York"
    assert resolve_timezone("bad/zone", "US") == "America/Chicago"
    assert resolve_timezone("", "XX") == "UTC"
