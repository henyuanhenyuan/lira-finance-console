"""MCP 服务端：把 7 个工具以 MCP 协议对外暴露（stdio）。

启动：python -m app.mcp_server
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import db, tools

mcp = MCPServer("lira-financial")

_ready = False


async def _ensure_pool() -> None:
    """在服务器自己的事件循环里建池，避免 asyncpg 连接跨循环复用。"""
    global _ready
    if not _ready:
        await db.init_pool()
        _ready = True


async def _call(name: str, args: dict) -> dict:
    await _ensure_pool()
    try:
        result, _ms = await tools.call(name, args)
    except tools.ToolError as exc:
        # 校验类错误回给客户端，不让它变成服务器内部异常
        return {"error": str(exc)}
    return result


@mcp.tool()
async def list_metrics() -> dict:
    """列出全部财务指标的机器名、中文名与口径。"""
    return await _call("list_metrics", {})


@mcp.tool()
async def run_sql(sql: str) -> dict:
    """在 mart/raw/agent/kb/eval 只读视图上执行受限 SELECT。"""
    return await _call("run_sql", {"sql": sql})


@mcp.tool()
async def get_metric_series(metric: str, days: int = 30) -> dict:
    """取单个指标按天的序列。metric 见 list_metrics。"""
    return await _call("get_metric_series", {"metric": metric, "days": days})


@mcp.tool()
async def compare_period(metric: str, days: int = 7) -> dict:
    """比较当前窗口与上一窗口的同环比。"""
    return await _call("compare_period", {"metric": metric, "days": days})


@mcp.tool()
async def find_anomalies(days: int = 7) -> dict:
    """按 Z-score 找出毛利异动的 SKU。"""
    return await _call("find_anomalies", {"days": days})


@mcp.tool()
async def get_sku_detail(sku_id: str) -> dict:
    """取单个 SKU 的全量经营数据。"""
    return await _call("get_sku_detail", {"sku_id": sku_id})


@mcp.tool()
async def search_kb(query: str, k: int = 4) -> dict:
    """在财务口径知识库做 pgvector 混合检索。"""
    return await _call("search_kb", {"query": query, "k": k})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
