"""序列引擎 tick（M2 主体，M1 先落骨架保证 beat 拓扑完整）。"""
from app.celery_app import celery


@celery.task(name="app.modules.sequence.tasks.tick")
def tick() -> int:
    """每 5 分钟：捞 next_action_at 到点的 active 序列（FOR UPDATE SKIP LOCKED），
    生成 send_jobs（幂等键）并投递到点任务。M2 实现，见架构 §6.1。"""
    return 0
