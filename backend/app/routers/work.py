from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, runner, security

router = APIRouter(prefix="/api/work", tags=["work"])


class RunIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    kind: str = Field(default="diagnosis", max_length=32)


@router.get("/runs")
async def list_runs(limit: int = 20, user=Depends(security.current_user)):
    return {"items": await runner.list_runs(limit)}


@router.post("/runs")
async def create_run(body: RunIn, user=Depends(security.current_user)):
    run = await runner.execute(body.question, kind=body.kind, trigger="manual")
    await db.execute(
        "INSERT INTO ops.audit_log(actor,action,target,payload) VALUES($1,'run',$2,$3)",
        user["email"], str(run["id"]), db.as_json({"question": body.question}))
    return run


@router.get("/runs/{run_id}")
async def get_run(run_id: int, user=Depends(security.current_user)):
    try:
        return await runner.get_run(run_id)
    except KeyError:
        raise HTTPException(404, "运行不存在")
