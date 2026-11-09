"""Lira 财务智能体控制台 — FastAPI 入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, rag, security, seed
from .config import get_settings
from .routers import agents, auth, dashboard, settings as settings_router, work

log = logging.getLogger("lira")
ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_pool()
    await db.apply_schema()
    info = await seed.seed_if_empty()
    log.info("seed: %s", info)
    await db.refresh_marts()

    exists = await db.fetchval("SELECT COUNT(*) FROM ops.users")
    if not exists:
        await db.execute(
            "INSERT INTO ops.users(email,password_hash,display_name,role) VALUES($1,$2,$3,$4)",
            "admin@lira.local", security.hash_password("lira2026"), "Lira 管理员", "owner")

    chunks = await db.fetchval("SELECT COUNT(*) FROM kb.chunks")
    if not chunks:
        log.info("indexing kb: %s", await rag.index_all())

    connectors = await db.fetchval("SELECT COUNT(*) FROM ops.connectors")
    if not connectors:
        await db.execute(
            """INSERT INTO ops.connectors(kind,name,endpoint,config)
               VALUES('csv','本地订单文件','',$1)""",
            db.as_json({"note": "上传 CSV 后按行写入订单表",
                        "columns": "order_id,sku_id,buyer_id,ordered_at,qty,paid,channel"}),
        )
    yield
    await db.close_pool()


app = FastAPI(title=get_settings().app_name, version=get_settings().version, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, dashboard.router, work.router, agents.router, settings_router.router):
    app.include_router(r)


@app.get("/api/health")
async def health():
    return {"ok": True, "version": get_settings().version}


if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        target = DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
