from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db, eval_harness, rag, security, tools

router = APIRouter(prefix="/api/agents", tags=["agents"])


class ToggleIn(BaseModel):
    enabled: bool


@router.get("")
async def list_agents(user=Depends(security.current_user)):
    rows = await db.fetch(
        """SELECT a.*,
                  (SELECT COUNT(*) FROM agent.steps s WHERE s.agent_key=a.key) AS step_count,
                  (SELECT COUNT(*) FROM agent.runs r WHERE r.result->>'model' IS NOT NULL) AS _x
           FROM agent.agents a ORDER BY sort_order""")
    return {"items": [db.jsonable(dict(r)) for r in rows]}


@router.patch("/{key}")
async def toggle_agent(key: str, body: ToggleIn, user=Depends(security.current_user)):
    result = await db.execute("UPDATE agent.agents SET enabled=$2 WHERE key=$1", key, body.enabled)
    if result.endswith(" 0"):
        raise HTTPException(404, "智能体不存在")
    await db.execute("INSERT INTO ops.audit_log(actor,action,target,payload) VALUES($1,'toggle_agent',$2,$3)",
                     user["email"], key, db.as_json({"enabled": body.enabled}))
    return {"key": key, "enabled": body.enabled}


@router.get("/tools/all")
async def list_tools(user=Depends(security.current_user)):
    return {"items": await tools.specs()}


@router.get("/kb")
async def kb_docs(user=Depends(security.current_user)):
    docs = await db.fetch(
        """SELECT d.id,d.slug,d.title,d.source,
                  (SELECT COUNT(*) FROM kb.chunks c WHERE c.doc_id=d.id) AS chunks
           FROM kb.docs d ORDER BY d.id""")
    return {"items": [db.jsonable(dict(r)) for r in docs]}


@router.post("/kb/reindex")
async def kb_reindex(user=Depends(security.current_user)):
    result = await rag.index_all(force=True)
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'reindex_kb','kb')",
                     user["email"])
    return result


@router.get("/evals/cases")
async def eval_cases(user=Depends(security.current_user)):
    rows = await db.fetch("SELECT * FROM eval.cases ORDER BY id")
    return {"items": [db.jsonable(dict(r)) for r in rows]}


@router.get("/evals/history")
async def eval_history(limit: int = 10, user=Depends(security.current_user)):
    return {"items": await eval_harness.history(limit)}


@router.post("/evals/run")
async def eval_run(limit: int | None = None, user=Depends(security.current_user)):
    result = await eval_harness.run_eval(limit)
    await db.execute("INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'run_eval',$2)",
                     user["email"], str(result["id"]))
    return result
