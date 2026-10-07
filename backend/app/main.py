"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

import re
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.core.session_context import session_scope

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 幂等：空库/缺表缺列时自动建，保证全新克隆启动即可用
    if (
        settings.llm_provider.lower() == "deepseek"
        and not Path("data/vectors-local-v1.db").exists()
    ):
        from app.knowledge.reindex import rebuild_local_index

        rebuild_local_index()
    yield


app = FastAPI(
    title="EduMind API",
    version="0.1.0",
    description="多模态 AI 互动式教学智能体后端",
    lifespan=lifespan,
)


@app.middleware("http")
async def scoped_request(request, call_next):
    header = request.headers.get("X-EduMind-Session")
    query = request.query_params.get("session_id")
    scope = header or query or "legacy"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", scope) or (header and query and header != query):
        return JSONResponse(status_code=400, content={"detail": "会话标识无效"})
    token = session_scope.set(scope)
    try:
        return await call_next(request)
    finally:
        session_scope.reset(token)


app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}
