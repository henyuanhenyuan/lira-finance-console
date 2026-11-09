"""执行一次 Agent Run：落库 run / steps / insight。"""

from __future__ import annotations

import time
from typing import Any

from . import db, graph


async def execute(question: str, *, kind: str = "diagnosis", trigger: str = "manual",
                  title: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = await db.fetchval(
        """INSERT INTO agent.runs(kind,title,status,trigger)
           VALUES($1,$2,'running',$3) RETURNING id""",
        kind, title or question[:60], trigger,
    )

    error: str | None = None
    try:
        state = await graph.run(question, scope=kind)
    except Exception as exc:  # noqa: BLE001
        state = {"question": question, "steps": [], "insight": {}, "model": "",
                 "tokens_in": 0, "tokens_out": 0, "cost": 0.0}
        error = str(exc)

    latency = int((time.perf_counter() - started) * 1000)
    insight = state.get("insight") or {}

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            for s in state.get("steps", []):
                await conn.execute(
                    """INSERT INTO agent.steps(run_id,idx,agent_key,thought,tool,args,observation,latency_ms,tokens)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    run_id, s["idx"], s["agent_key"], s["thought"], s["tool"],
                    db.as_json(s["args"]), db.as_json(s["observation"]),
                    s["latency_ms"], s["tokens"],
                )
            status = "failed" if error else "succeeded"
            await conn.execute(
                """UPDATE agent.runs
                   SET status=$2, finished_at=now(), latency_ms=$3,
                       tokens_in=$4, tokens_out=$5, cost_usd=$6,
                       model=$7, result=$8
                   WHERE id=$1""",
                run_id, status, latency,
                state.get("tokens_in", 0), state.get("tokens_out", 0),
                state.get("cost", 0.0), state.get("model", ""),
                db.as_json({"insight": insight,
                            "facts": state.get("facts", {}),
                            "error": error}),
            )
            if insight.get("headline"):
                await conn.execute(
                    """INSERT INTO agent.insights(scope,ref,headline,drivers,confidence,evidence,actions,model)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8)""",
                    kind, str(run_id), insight["headline"],
                    db.as_json(insight.get("drivers", [])),
                    float(insight.get("confidence", 0)),
                    db.as_json(insight.get("evidence", [])),
                    db.as_json(insight.get("actions", [])),
                    state.get("model", ""),
                )

    return await get_run(run_id)


async def get_run(run_id: int) -> dict[str, Any]:
    run = await db.fetchrow("SELECT * FROM agent.runs WHERE id=$1", run_id)
    if not run:
        raise KeyError(run_id)
    steps = await db.fetch(
        "SELECT * FROM agent.steps WHERE run_id=$1 ORDER BY idx", run_id)
    return {**db.jsonable(dict(run)),
            "steps": [db.jsonable(dict(s)) for s in steps]}


async def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """SELECT id,kind,title,status,trigger,model,started_at,finished_at,
                  latency_ms,tokens_in,tokens_out,cost_usd,
                  result->'insight'->>'headline' AS headline
           FROM agent.runs ORDER BY id DESC LIMIT $1""",
        limit,
    )
    return [db.jsonable(dict(r)) for r in rows]
