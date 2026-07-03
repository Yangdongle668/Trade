"""收件轮询（架构 §7）：每 3 分钟增量拉取 → 入向处理器。"""
import structlog
from sqlalchemy import select

from app.celery_app import celery
from app.core.db import SessionLocal
from app.modules.mailbox.inbound import poll_mailbox
from app.modules.mailbox.models import Mailbox

log = structlog.get_logger()


@celery.task(name="app.modules.mailbox.tasks.poll_all")
def poll_all() -> int:
    with SessionLocal() as db:
        ids = db.execute(select(Mailbox.id).where(
            Mailbox.health != "paused")).scalars().all()
    for mid in ids:
        poll_one.delay(str(mid))
    return len(ids)


@celery.task(name="app.modules.mailbox.tasks.poll_one", bind=True, max_retries=1)
def poll_one(self, mailbox_id: str) -> dict:
    from app.modules.triage.processor import process_inbound
    stats = {"fetched": 0, "processed": 0}
    with SessionLocal() as db:
        mailbox = db.get(Mailbox, mailbox_id)
        if mailbox is None:
            return stats
        mails, cursor = poll_mailbox(mailbox)
        mailbox.poll_cursor = cursor
        db.commit()
        stats["fetched"] = len(mails)
        for mail in mails:
            result = process_inbound(db, mailbox, mail)
            if result not in ("dup", "unmatched"):
                stats["processed"] += 1
    if stats["fetched"]:
        log.info("mailbox.polled", mailbox=mailbox_id, **stats)
    return stats
