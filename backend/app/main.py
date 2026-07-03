from fastapi import FastAPI

from app.core.logging import setup_logging
from app.modules.brandkit.router import router as brandkit_router
from app.modules.campaign.router import router as campaign_router
from app.modules.discovery.router import router as leads_router
from app.modules.identity.router import router as auth_router
from app.modules.campaign.reports import router as reports_router
from app.modules.mailbox.router import router as mailbox_router
from app.modules.sequence.router import enroll_router, router as sendjobs_router
from app.modules.triage.inbox_router import router as inbox_router
from app.modules.triage.router import router as public_router


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="远航开发助手 API",
        version="0.1.0",
        description="外贸 AI 客户开发助手（Outreach Copilot）— 前端经 OpenAPI 生成 TS 客户端",
    )
    app.include_router(auth_router)
    app.include_router(brandkit_router)
    app.include_router(campaign_router)
    app.include_router(leads_router)
    app.include_router(mailbox_router)
    app.include_router(sendjobs_router)
    app.include_router(enroll_router)
    app.include_router(public_router)
    app.include_router(inbox_router)
    app.include_router(reports_router)

    @app.get("/api/health", tags=["ops"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
