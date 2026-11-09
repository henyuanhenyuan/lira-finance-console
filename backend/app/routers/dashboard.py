from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db, metrics, runner, security

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/catalogue")
async def catalogue(user=Depends(security.current_user)):
    return metrics.catalogue()


@router.get("/overview")
async def overview(days: int = Query(7, ge=1, le=90), user=Depends(security.current_user)):
    return {"days": days, "metrics": await metrics.overview(days)}


@router.get("/series")
async def series(metric: str, days: int = Query(30, ge=5, le=90),
                 user=Depends(security.current_user)):
    if metric not in metrics.SERIES_SQL:
        raise HTTPException(400, f"未知指标: {metric}")
    return {"metric": metric, "points": await metrics.series(metric, days)}


@router.get("/rankings")
async def rankings(metric: str = "gross_margin", days: int = Query(7, ge=1, le=90),
                   asc: bool = True, limit: int = Query(8, ge=3, le=30),
                   user=Depends(security.current_user)):
    if metric not in metrics.RANKING_METRICS:
        raise HTTPException(400, f"不支持的排行指标: {metric}")
    return {"items": await metrics.sku_ranking(metric, days, limit, asc)}


@router.get("/categories")
async def categories(days: int = Query(30, ge=5, le=90), user=Depends(security.current_user)):
    return {"items": await metrics.category_mix(days)}


@router.get("/anomalies")
async def anomalies(days: int = Query(7, ge=3, le=90), user=Depends(security.current_user)):
    return {"items": await metrics.anomalies(days)}


@router.get("/insight")
async def latest_insight(scope: str = "dashboard", user=Depends(security.current_user)):
    row = await db.fetchrow(
        """SELECT id,headline,drivers,confidence,evidence,actions,model,created_at
           FROM agent.insights WHERE scope=$1 ORDER BY id DESC LIMIT 1""", scope)
    return {"insight": db.jsonable(dict(row)) if row else None}


@router.post("/insight/refresh")
async def refresh_insight(user=Depends(security.current_user)):
    question = ("本周贡献毛利为什么变化？找出异常 SKU 并给出处理建议，"
                "同时说明相关的口径规则。")
    run = await runner.execute(question, kind="dashboard", trigger="dashboard",
                               title="大屏实时研判")
    row = await db.fetchrow(
        """SELECT id,headline,drivers,confidence,evidence,actions,model,created_at
           FROM agent.insights WHERE scope='dashboard' ORDER BY id DESC LIMIT 1""")
    return {"run_id": run["id"], "latency_ms": run["latency_ms"],
            "insight": db.jsonable(dict(row)) if row else None,
            "steps": run.get("steps", [])}
