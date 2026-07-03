"""收件轮询（M3 主体，M1 先落骨架保证 beat 拓扑完整）。"""
from app.celery_app import celery


@celery.task(name="app.modules.mailbox.tasks.poll_all")
def poll_all() -> int:
    """每 3 分钟：Gmail history / Graph delta / IMAP UID 游标增量拉取。M3 实现，见架构 §7。"""
    return 0
