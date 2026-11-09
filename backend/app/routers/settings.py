from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, ingest, llm, metrics, security
from ..config import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

MAX_USERS = 5
ROLES = ("owner", "analyst", "viewer")
CONNECTOR_KINDS = ("csv", "http", "taobao", "erp")


def _owner(user=Depends(security.current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "仅管理员可执行该操作")
    return user


# ---------------- 概览 ----------------
@router.get("")
async def settings_snapshot(user=Depends(security.current_user)):
    s = get_settings()
    models = await db.fetch("SELECT * FROM ops.model_configs ORDER BY purpose, id")
    stats = await db.fetchrow(
        """SELECT (SELECT COUNT(*) FROM raw.skus) AS skus,
                  (SELECT COUNT(*) FROM raw.orders) AS orders,
                  (SELECT COUNT(*) FROM kb.chunks) AS chunks,
                  (SELECT COUNT(*) FROM agent.runs) AS runs,
                  (SELECT COUNT(*) FROM agent.insights) AS insights,
                  (SELECT COUNT(*) FROM ops.users) AS users,
                  (SELECT COUNT(*) FROM ops.connectors) AS connectors""")
    return {
        "app": {"name": s.app_name, "version": s.version},
        "llm": {
            "provider": s.llm_provider, "model": s.llm_model,
            "base_url": s.llm_base_url, "configured": bool(s.llm_api_key),
            "test_model": s.test_llm_model, "test_base_url": s.test_llm_base_url,
        },
        "metric_version": metrics.VERSION,
        "max_react_steps": s.max_react_steps,
        "max_users": MAX_USERS,
        "models": [db.jsonable(dict(r)) for r in models],
        "stats": db.jsonable(dict(stats)),
        "pricing": {k: {"in": v[0], "out": v[1]} for k, v in llm.PRICES.items()},
    }


# ---------------- 模型路由 ----------------
class ModelIn(BaseModel):
    provider: str = Field(max_length=40)
    model: str = Field(max_length=80)
    base_url: str = Field(default="", max_length=200)
    purpose: str = Field(default="production", max_length=20)
    note: str = Field(default="", max_length=200)


class DefaultIn(BaseModel):
    id: int


@router.post("/models")
async def add_model(body: ModelIn, user=Depends(security.current_user)):
    rid = await db.fetchval(
        """INSERT INTO ops.model_configs(provider,model,base_url,purpose,note)
           VALUES($1,$2,$3,$4,$5) RETURNING id""",
        body.provider, body.model, body.base_url, body.purpose, body.note)
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'add_model',$2)",
                     user["email"], body.model)
    return {"id": rid}


@router.post("/models/default")
async def set_default(body: DefaultIn, user=Depends(_owner)):
    row = await db.fetchrow("SELECT purpose FROM ops.model_configs WHERE id=$1", body.id)
    if not row:
        raise HTTPException(404, "模型不存在")
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE ops.model_configs SET is_default=false WHERE purpose=$1",
                               row["purpose"])
            await conn.execute("UPDATE ops.model_configs SET is_default=true WHERE id=$1", body.id)
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'set_default_model',$2)",
                     user["email"], str(body.id))
    return {"ok": True, "id": body.id}


# ---------------- 账号（最多 5 人） ----------------
class UserIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    display_name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="analyst")


class UserPatch(BaseModel):
    status: str | None = None
    role: str | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/users")
async def users(user=Depends(security.current_user)):
    rows = await db.fetch(
        """SELECT id,email,display_name,role,status,last_login_at,created_at
           FROM ops.users ORDER BY id""")
    return {"items": [db.jsonable(dict(r)) for r in rows], "max": MAX_USERS}


@router.post("/users")
async def create_user(body: UserIn, user=Depends(_owner)):
    if body.role not in ROLES:
        raise HTTPException(400, f"角色必须是 {ROLES}")
    count = await db.fetchval("SELECT COUNT(*) FROM ops.users")
    if count >= MAX_USERS:
        raise HTTPException(400, f"最多只能创建 {MAX_USERS} 个账号")
    exists = await db.fetchval("SELECT 1 FROM ops.users WHERE lower(email)=lower($1)", body.email)
    if exists:
        raise HTTPException(400, "该邮箱已存在")
    uid = await db.fetchval(
        """INSERT INTO ops.users(email,password_hash,display_name,role,status)
           VALUES($1,$2,$3,$4,'active') RETURNING id""",
        body.email.lower(), security.hash_password(body.password), body.display_name, body.role)
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'create_user',$2)",
                     user["email"], body.email)
    return {"id": uid}


@router.patch("/users/{uid}")
async def patch_user(uid: int, body: UserPatch, user=Depends(_owner)):
    row = await db.fetchrow("SELECT id,role,status FROM ops.users WHERE id=$1", uid)
    if not row:
        raise HTTPException(404, "账号不存在")
    if uid == user["id"] and body.status == "disabled":
        raise HTTPException(400, "不能停用自己的账号")
    if row["role"] == "owner" and body.role and body.role != "owner":
        owners = await db.fetchval("SELECT COUNT(*) FROM ops.users WHERE role='owner' AND status='active'")
        if owners <= 1:
            raise HTTPException(400, "至少保留一名启用的管理员")
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise HTTPException(400, "状态只能是 active / disabled")
        await db.execute("UPDATE ops.users SET status=$2 WHERE id=$1", uid, body.status)
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(400, f"角色必须是 {ROLES}")
        await db.execute("UPDATE ops.users SET role=$2 WHERE id=$1", uid, body.role)
    await db.execute(
        "INSERT INTO ops.audit_log(actor,action,target,payload) VALUES($1,'patch_user',$2,$3)",
        user["email"], str(uid), db.as_json(body.model_dump(exclude_none=True)))
    return {"ok": True}


@router.post("/users/{uid}/password")
async def reset_password(uid: int, body: PasswordReset, user=Depends(_owner)):
    exists = await db.fetchval("SELECT 1 FROM ops.users WHERE id=$1", uid)
    if not exists:
        raise HTTPException(404, "账号不存在")
    await db.execute("UPDATE ops.users SET password_hash=$2 WHERE id=$1",
                     uid, security.hash_password(body.new_password))
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'reset_password',$2)",
                     user["email"], str(uid))
    return {"ok": True}


# ---------------- 接入模块 ----------------
class ConnectorIn(BaseModel):
    kind: str = Field(max_length=16)
    name: str = Field(min_length=1, max_length=60)
    endpoint: str = Field(default="", max_length=300)
    config: dict[str, Any] = Field(default_factory=dict)


class SyncIn(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/connectors")
async def list_connectors(user=Depends(security.current_user)):
    rows = await db.fetch("SELECT * FROM ops.connectors ORDER BY id")
    return {"items": [db.jsonable(dict(r)) for r in rows], "kinds": CONNECTOR_KINDS}


@router.post("/connectors")
async def create_connector(body: ConnectorIn, user=Depends(_owner)):
    if body.kind not in CONNECTOR_KINDS:
        raise HTTPException(400, f"类型必须是 {CONNECTOR_KINDS}")
    if body.kind != "csv" and not body.endpoint.startswith(("http://", "https://")):
        raise HTTPException(400, "接口地址必须是 http(s) URL")
    cid = await db.fetchval(
        """INSERT INTO ops.connectors(kind,name,endpoint,config)
           VALUES($1,$2,$3,$4) RETURNING id""",
        body.kind, body.name, body.endpoint, db.as_json(body.config))
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'add_connector',$2)",
                     user["email"], body.name)
    return {"id": cid}


@router.patch("/connectors/{cid}")
async def toggle_connector(cid: int, body: dict, user=Depends(_owner)):
    enabled = bool(body.get("enabled", True))
    res = await db.execute("UPDATE ops.connectors SET enabled=$2 WHERE id=$1", cid, enabled)
    if res.endswith(" 0"):
        raise HTTPException(404, "接入项不存在")
    return {"id": cid, "enabled": enabled}


@router.delete("/connectors/{cid}")
async def delete_connector(cid: int, user=Depends(_owner)):
    res = await db.execute("DELETE FROM ops.connectors WHERE id=$1", cid)
    if res.endswith(" 0"):
        raise HTTPException(404, "接入项不存在")
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'delete_connector',$2)",
                     user["email"], str(cid))
    return {"ok": True}


@router.post("/connectors/{cid}/test")
async def test_connector(cid: int, user=Depends(security.current_user)):
    row = await db.fetchrow("SELECT * FROM ops.connectors WHERE id=$1", cid)
    if not row:
        raise HTTPException(404, "接入项不存在")

    if row["kind"] == "csv":
        await db.execute(
            "UPDATE ops.connectors SET status='ready', last_tested_at=now(), last_test_ms=0 WHERE id=$1", cid)
        return {"ok": True, "message": "本地文件接入，无需连通性测试", "ms": 0}

    started = time.perf_counter()
    ok, message = False, ""
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
            resp = await client.get(row["endpoint"], headers={"Accept": "application/json"})
        ok = resp.status_code < 400
        message = f"HTTP {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        message = f"连接失败: {type(exc).__name__}"
    ms = int((time.perf_counter() - started) * 1000)
    await db.execute(
        "UPDATE ops.connectors SET status=$2, last_tested_at=now(), last_test_ms=$3 WHERE id=$1",
        cid, "ready" if ok else "error", ms)
    await db.execute(
        "INSERT INTO ops.audit_log(actor,action,target,payload) VALUES($1,'test_connector',$2,$3)",
        user["email"], str(cid), db.as_json({"ok": ok, "msg": message}))
    return {"ok": ok, "message": message, "ms": ms}


@router.post("/connectors/{cid}/sync")
async def sync_connector(cid: int, body: SyncIn, user=Depends(security.current_user)):
    row = await db.fetchrow("SELECT * FROM ops.connectors WHERE id=$1", cid)
    if not row:
        raise HTTPException(404, "接入项不存在")
    if not row["enabled"]:
        raise HTTPException(400, "该接入项已停用")

    rows = body.rows
    if row["kind"] != "csv":
        if not row["endpoint"]:
            raise HTTPException(400, "该接入项没有配置接口地址")
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(row["endpoint"], headers={"Accept": "application/json"})
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            await db.execute("UPDATE ops.connectors SET status='error' WHERE id=$1", cid)
            raise HTTPException(502, f"拉取失败: {type(exc).__name__}") from exc
        rows = payload.get("orders") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise HTTPException(400, "接口需返回订单数组，或 {\"orders\": [...]}")
    if not rows:
        raise HTTPException(400, "没有可导入的数据行")

    try:
        result = await ingest.ingest_orders(rows, source=row["name"])
    except ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc

    await db.execute(
        """UPDATE ops.connectors
           SET status='synced', last_sync_at=now(), rows_synced=rows_synced+$2
           WHERE id=$1""",
        cid, result["accepted"])
    await db.execute(
        "INSERT INTO ops.audit_log(actor,action,target,payload) VALUES($1,'sync_connector',$2,$3)",
        user["email"], str(cid), db.as_json({"accepted": result["accepted"]}))
    return result


# ---------------- 审计 ----------------
@router.get("/audit")
async def audit(limit: int = 30, user=Depends(security.current_user)):
    rows = await db.fetch(
        "SELECT id,actor,action,target,created_at FROM ops.audit_log ORDER BY id DESC LIMIT $1",
        limit)
    return {"items": [db.jsonable(dict(r)) for r in rows]}
