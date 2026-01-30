from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.executions import router as executions_router
from app.api.oauth import router as oauth_router
from app.config import settings
from app.db import init_db


def create_app() -> FastAPI:
    app = FastAPI(title="AgentSocialS Backend", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    app.include_router(executions_router)
    app.include_router(oauth_router)
    return app


app = create_app()

