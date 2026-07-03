import structlog

from app.celery_app import celery
from app.core.db import SessionLocal
from app.modules.sequence import service

log = structlog.get_logger()


@celery.task(name="app.modules.sequence.tasks.tick")
def tick() -> dict:
    """每 5 分钟：到点序列生成 send_job；到点已批准 job 投递执行（架构 §6.1）。"""
    with SessionLocal() as db:
        stats = service.tick(db)
    if stats["jobs_created"] or stats["jobs_dispatched"]:
        log.info("sequence.tick", **stats)
    return stats


@celery.task(name="app.modules.sequence.tasks.execute_send_job", bind=True, max_retries=0)
def execute_send_job(self, job_id: str) -> str:
    """发送执行：重试语义由 service 层控制（回 approved+顺延），不用 Celery retry。"""
    with SessionLocal() as db:
        result = service.execute_send(db, job_id)
    log.info("send.executed", job=job_id, result=result)
    return result
