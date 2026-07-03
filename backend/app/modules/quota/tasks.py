from app.celery_app import celery
from app.core.db import SessionLocal


@celery.task(name="app.modules.quota.tasks.daily_reset")
def daily_reset() -> int:
    """日配额按 period 自然切换；此处推进发信身份预热爬坡（架构 §6.3）。"""
    from app.modules.mailbox.service import advance_warmup
    with SessionLocal() as db:
        advanced = advance_warmup(db)
        db.commit()
    return advanced
