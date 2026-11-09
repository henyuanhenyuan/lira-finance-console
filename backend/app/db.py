"""asyncpg 连接池 + 建表 + 种子。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import asyncpg

from .config import get_settings

_pool: asyncpg.Pool | None = None
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


async def _configure_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text")
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text")


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=s.database_url, min_size=1, max_size=10, command_timeout=60,
            init=_configure_conn,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("连接池未初始化")
    return _pool


async def apply_schema() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool().acquire() as conn:
        await conn.execute(sql)


async def refresh_marts() -> None:
    """raw 变更后重算物化视图。"""
    async with pool().acquire() as conn:
        await conn.execute("REFRESH MATERIALIZED VIEW mart.sku_daily")
        await conn.execute("REFRESH MATERIALIZED VIEW mart.metric_daily")


async def fetch(sql: str, *args: Any) -> list[asyncpg.Record]:
    async with pool().acquire() as conn:
        return await conn.fetch(sql, *args)


async def fetchrow(sql: str, *args: Any) -> asyncpg.Record | None:
    async with pool().acquire() as conn:
        return await conn.fetchrow(sql, *args)


async def fetchval(sql: str, *args: Any) -> Any:
    async with pool().acquire() as conn:
        return await conn.fetchval(sql, *args)


async def execute(sql: str, *args: Any) -> str:
    async with pool().acquire() as conn:
        return await conn.execute(sql, *args)


def jsonable(value: Any) -> Any:
    """NUMERIC/Decimal → float，date → iso，JSONB → dict，便于直接进 JSON。"""
    import datetime as dt
    import decimal

    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def as_json(value: Any) -> str:
    return json.dumps(jsonable(value), ensure_ascii=False)
