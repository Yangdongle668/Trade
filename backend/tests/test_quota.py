import uuid

import pytest

from app.modules.quota.service import QuotaExceeded, check_and_increment


def test_quota_blocks_over_limit(db):
    tid = uuid.uuid4()
    for _ in range(3):
        check_and_increment(db, tid, "leads_per_month", limit=3)
    with pytest.raises(QuotaExceeded):
        check_and_increment(db, tid, "leads_per_month", limit=3)


def test_quota_isolated_by_tenant(db):
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    check_and_increment(db, t1, "leads_per_month", limit=1)
    check_and_increment(db, t2, "leads_per_month", limit=1)  # 各自独立，不应抛错
