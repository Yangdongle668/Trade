from app.celery_app import celery


@celery.task(name="app.modules.quota.tasks.daily_reset")
def daily_reset() -> None:
    """日配额按 period 自然切换，无需清零；此任务做健康巡检占位（M2 扩展：预热爬坡推进）。"""
    return None
