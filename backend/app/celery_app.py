"""Celery 实例与调度。

ADR-4：数天级长排程一律存 Postgres（next_action_at / scheduled_at），
Celery 只承担即时执行、重试与并发控制；beat 只发分钟级 tick。
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

celery = Celery("outreach", broker=get_settings().redis_url, backend=None)

celery.conf.update(
    task_default_queue="maintenance",
    task_routes={
        "app.modules.discovery.*": {"queue": "discovery"},
        "app.modules.sequence.*": {"queue": "sequence"},
        "app.modules.mailbox.*": {"queue": "mailbox"},
    },
    task_acks_late=True,           # worker 崩溃不丢任务
    worker_prefetch_multiplier=1,  # 配合 acks_late，避免任务囤积在单 worker
    timezone="UTC",
    beat_schedule={
        # 序列引擎 tick：捞出 next_action_at 到点的序列，生成/投递 send_jobs（§6.1）
        "sequence-tick": {
            "task": "app.modules.sequence.tasks.tick",
            "schedule": 300.0,
        },
        # 收件轮询：Gmail history / Graph delta / IMAP UID 游标（§7，<5 分钟时效）
        "mailbox-poll": {
            "task": "app.modules.mailbox.tasks.poll_all",
            "schedule": 180.0,
        },
        # 线索发现夜间批（北京时间深夜 ≈ UTC 18:00 起）
        "discovery-nightly": {
            "task": "app.modules.discovery.tasks.run_due_campaigns",
            "schedule": crontab(hour=18, minute=0),
        },
        # 配额日重置与健康巡检
        "maintenance-daily": {
            "task": "app.modules.quota.tasks.daily_reset",
            "schedule": crontab(hour=0, minute=5),
        },
    },
)

celery.autodiscover_tasks(
    [
        "app.modules.discovery",
        "app.modules.sequence",
        "app.modules.mailbox",
        "app.modules.quota",
    ]
)
