from fastapi import FastAPI

from app.core.logging import setup_logging
from app.modules.brandkit.router import router as brandkit_router
from app.modules.campaign.router import router as campaign_router
from app.modules.identity.router import router as auth_router


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

    @app.get("/api/health", tags=["ops"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
