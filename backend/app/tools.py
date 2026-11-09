"""MCP 工具集：Agent 访问数据的唯一通道。

每个工具都有 JSON Schema、只读约束与调用统计（喂给评测）。
"""

from __future__ import annotations

import re
import time
from typing import Any, Awaitable, Callable

from . import db, metrics, rag

_SAFE_SQL = re.compile(r"^\s*(select|with)\b", re.I)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|copy|vacuum|"
    r"pg_read_file|pg_sleep|dblink|lo_import|lo_export)\b", re.I)
_ALLOWED_SCHEMA = re.compile(r"\b(mart|raw|agent|kb|eval)\.[a-z_]+", re.I)


class ToolError(Exception):
    pass


def _guard_sql(sql: str) -> str:
    s = sql.strip().rstrip(";")
    if not _SAFE_SQL.match(s):
        raise ToolError("只允许只读 SELECT / WITH 查询")
    if _FORBIDDEN.search(s):
        raise ToolError("检测到写操作或危险函数，已拒绝")
    if ";" in s:
        raise ToolError("不允许多语句执行")
    if not _ALLOWED_SCHEMA.search(s):
        raise ToolError("查询必须限定在 mart / raw / agent / kb / eval 视图内")
    if " limit " not in s.lower():
        s += " LIMIT 200"
    return s


async def _run_sql(args: dict) -> dict:
    sql = _guard_sql(str(args.get("sql", "")))
    rows = await db.fetch(sql)
    return {"rows": [db.jsonable(dict(r)) for r in rows][:200], "count": len(rows)}


async def _list_metrics(_: dict) -> dict:
    return metrics.catalogue()


async def _get_metric_series(args: dict) -> dict:
    metric = str(args.get("metric", "gross_margin"))
    days = int(args.get("days", 30))
    data = await metrics.series(metric, days)
    return {"metric": metric, "days": days, "points": data,
            "total": round(sum(p["value"] or 0 for p in data), 2)}


async def _compare_period(args: dict) -> dict:
    metric = str(args.get("metric", "gross_margin"))
    days = int(args.get("days", 7))
    return await metrics.compare(metric, days)


async def _find_anomalies(args: dict) -> dict:
    days = int(args.get("days", 7))
    items = await metrics.anomalies(days)
    return {"days": days, "items": items,
            "count": len(items),
            "worst": items[0]["sku_id"] if items else None}


async def _get_sku_detail(args: dict) -> dict:
    sku = str(args.get("sku_id", ""))
    detail = await metrics.sku_detail(sku)
    if not detail:
        raise ToolError(f"未找到 SKU: {sku}")
    return detail


async def _search_kb(args: dict) -> dict:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query 不能为空")
    k = int(args.get("k", 4))
    hits = await rag.search(query, k)
    return {"query": query, "hits": hits,
            "citations": [h["chunk_id"] for h in hits]}


IMPLS: dict[str, Callable[[dict], Awaitable[dict]]] = {
    "run_sql": _run_sql,
    "list_metrics": _list_metrics,
    "get_metric_series": _get_metric_series,
    "compare_period": _compare_period,
    "find_anomalies": _find_anomalies,
    "get_sku_detail": _get_sku_detail,
    "search_kb": _search_kb,
}


async def call(name: str, args: dict[str, Any]) -> tuple[dict, int]:
    """执行工具，返回 (结果, 耗时毫秒)，并累加调用统计。"""
    impl = IMPLS.get(name)
    if impl is None:
        raise ToolError(f"未知工具: {name}")
    started = time.perf_counter()
    result = await impl(args)
    elapsed = int((time.perf_counter() - started) * 1000)
    await db.execute(
        """UPDATE agent.tools
           SET calls = calls + 1,
               avg_latency = CASE WHEN calls = 0 THEN $2 ELSE (avg_latency * calls + $2) / (calls + 1) END
           WHERE key = $1""",
        name, elapsed,
    )
    return result, elapsed


async def specs() -> list[dict]:
    rows = await db.fetch(
        "SELECT key, name, description, input_schema, calls, avg_latency, enabled"
        " FROM agent.tools ORDER BY key")
    return [db.jsonable(dict(r)) for r in rows]
