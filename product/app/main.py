"""FastAPI surface for the local profit diagnosis app."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import analysis, connectors, costs, db, imports, llm, ops, semantic
from .scheduler import SyncScheduler

_log = logging.getLogger("lira.api")

ROOT = Path(__file__).resolve().parents[1]
_WEB_DIST = Path(os.environ.get("LIRA_WEB_ROOT", str(ROOT / "web" / "dist")))
STATIC = _WEB_DIST if (_WEB_DIST / "index.html").exists() else ROOT / "static"
_LEGACY_STATIC = ROOT / "static"

_scheduler = SyncScheduler()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.ensure_db()
    _scheduler.start()
    try:
        yield
    finally:
        _scheduler.stop()


app = FastAPI(title="Lira Local", version=ops.VERSION, lifespan=lifespan)
if (_LEGACY_STATIC / "app.js").exists():
    app.mount("/static", StaticFiles(directory=str(_LEGACY_STATIC)), name="static")
if (STATIC / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC / "assets")), name="assets")


@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"http_{exc.status_code}",
                "message": str(exc.detail),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": "请求参数不符合约定",
            }
        },
    )


@app.exception_handler(Exception)
async def _internal_error(_: Request, exc: Exception) -> JSONResponse:
    _log.exception("unhandled request failure")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal", "message": "服务内部错误"}},
    )


_PIN = os.environ.get("LIRA_PIN", "").strip()


@app.middleware("http")
async def _pin_guard(request: Request, call_next):
    if (
        _PIN
        and request.url.path.startswith("/api")
        and request.url.path != "/api/v1/ops/health"
    ):
        supplied = request.headers.get("X-Lira-Pin") or request.cookies.get("lira_pin")
        if supplied != _PIN:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "auth_required", "message": "需要访问 PIN"}},
            )
    return await call_next(request)


class AckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["adopted", "ignored", "later"]
    note: str = ""


class CostConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str
    mapping: dict[str, str | None]


class ImportConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    upload_id: str
    mapping: dict[str, str | None]
    replace: bool = True


class AliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_sku: str = Field(min_length=1)
    merchant_sku: str = Field(min_length=1)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    start: dt.date | None = None
    end: dt.date | None = None


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/overview")
def overview(
    start: dt.date | None = Query(None),
    end: dt.date | None = Query(None),
) -> dict:
    with db.session() as con:
        try:
            data = analysis.overview(con, start, end)
            db.record_analysis(
                con, kind="overview", question="", intent="", result=data
            )
            return data
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/loss-skus")
def loss_skus(
    start: dt.date | None = Query(None),
    end: dt.date | None = Query(None),
    min_loss: float = Query(0.0, ge=0),
) -> dict:
    with db.session() as con:
        try:
            return analysis.loss_skus(con, start, end, min_loss)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ad-waste")
def ad_waste(
    start: dt.date | None = Query(None),
    end: dt.date | None = Query(None),
) -> dict:
    with db.session() as con:
        try:
            return analysis.ad_waste(con, start, end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/skus/{sku}")
def sku_detail(
    sku: str,
    start: dt.date | None = Query(None),
    end: dt.date | None = Query(None),
) -> dict:
    with db.session() as con:
        try:
            result = analysis.sku_detail(con, sku, start, end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"没有这个 SKU：{sku}")
    return result


@app.get("/api/data-health")
def data_health() -> dict:
    with db.session() as con:
        return analysis.data_health(con)


@app.post("/api/sync")
def sync() -> dict:
    scanned = imports.scan_inbox()
    counts = db.reload()
    return {"status": "ok", "scanned": scanned, **counts}


@app.post("/api/demo/reset")
def demo_reset() -> dict:
    return {"status": "ok", **db.reset_sample()}


@app.post("/api/import/preview")
async def import_preview(
    dataset: str = Query(..., description="orders / refunds / ads"),
    file: UploadFile = File(...),
) -> dict:
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 10MB")
    try:
        upload_id, path = costs.save_upload(file.filename or "upload.csv", data)
        return imports.preview(dataset, upload_id, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/import/confirm")
def import_confirm(body: ImportConfirm) -> dict:
    try:
        path = costs.path_for(body.upload_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with db.session() as con:
        try:
            result = imports.apply(
                con, body.dataset, path, body.mapping, path.name, replace=body.replace
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        overview = analysis.overview(con)
    return {**result, "cost_coverage": overview["cost_coverage"]}


@app.post("/api/import/scan")
def import_scan() -> dict:
    scanned = imports.scan_inbox()
    counts = db.reload()
    return {"status": "ok", "scanned": scanned, **counts}


@app.get("/api/import/status")
def import_status() -> dict:
    return {
        **imports.status(),
        "interval_s": _scheduler.interval,
        "watcher": _scheduler.mode,
        "model": llm.status(),
    }


@app.get("/api/connectors")
def connector_status() -> dict:
    return connectors.status()


@app.post("/api/connectors/{name}/configure")
def connector_configure(name: str, payload: dict[str, str]) -> dict:
    try:
        return connectors.configure(name, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/connectors/{name}/test")
def connector_test(name: str) -> dict:
    return connectors.test(name)


@app.delete("/api/connectors/{name}")
def connector_delete(name: str) -> dict:
    try:
        return connectors.delete(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/connectors/{name}/pull")
def connector_pull(
    name: str,
    start: dt.date = Query(...),
    end: dt.date = Query(...),
) -> dict:
    try:
        return connectors.pull(name, start.isoformat(), end.isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - connector failures are upstream
        _log.exception("connector pull failed")
        raise HTTPException(status_code=502, detail="连接器拉取失败") from exc


@app.get("/api/sku-aliases")
def sku_aliases() -> dict:
    with db.session() as con:
        rows = con.execute(
            "SELECT platform_sku_id, merchant_sku FROM raw.sku_alias "
            "ORDER BY platform_sku_id"
        ).fetchall()
        unresolved = con.execute(
            "SELECT DISTINCT o.sku FROM raw.orders AS o "
            "LEFT JOIN raw.sku_alias AS a ON a.platform_sku_id = o.sku "
            "LEFT JOIN raw.costs AS c ON c.sku = COALESCE(a.merchant_sku, o.sku) "
            "WHERE c.sku IS NULL ORDER BY o.sku"
        ).fetchall()
    return {
        "aliases": [
            {"platform_sku": row[0], "merchant_sku": row[1]} for row in rows
        ],
        "unresolved": [row[0] for row in unresolved],
    }


@app.post("/api/sku-aliases")
def sku_alias_upsert(body: AliasRequest) -> dict:
    with db.session() as con:
        con.execute(
            "DELETE FROM raw.sku_alias WHERE platform_sku_id = ?", [body.platform_sku]
        )
        con.execute(
            "INSERT INTO raw.sku_alias VALUES (?, ?, now())",
            [body.platform_sku, body.merchant_sku],
        )
        db.refresh_views(con)
        overview = analysis.overview(con)
    return {"status": "ok", "cost_coverage": overview["cost_coverage"]}


@app.delete("/api/sku-aliases/{platform_sku}")
def sku_alias_delete(platform_sku: str) -> dict:
    with db.session() as con:
        con.execute(
            "DELETE FROM raw.sku_alias WHERE platform_sku_id = ?", [platform_sku]
        )
        db.refresh_views(con)
    return {"status": "ok"}


@app.post("/api/ask")
def ask(body: AskRequest) -> dict:
    with db.session() as con:
        result = llm.answer_question(con, body.question, body.start, body.end)
        db.record_analysis(
            con,
            kind="ask",
            question=body.question,
            intent=result["intent"],
            result=result,
        )
        return result


@app.post("/api/costs/preview")
async def cost_preview(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="成本文件超过 10MB")
    try:
        upload_id, path = costs.save_upload(file.filename or "upload.csv", data)
        return costs.preview(upload_id, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/costs/confirm")
def cost_confirm(body: CostConfirm) -> dict:
    try:
        path = costs.path_for(body.upload_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with db.session() as con:
        try:
            result = costs.apply(con, path, body.mapping, path.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        overview = analysis.overview(con)
        health = analysis.data_health(con)

    return {
        **result,
        "cost_coverage": overview["cost_coverage"],
        "missing_skus": health["missing_skus"],
    }


@app.get("/api/costs/template")
def cost_template() -> Response:
    with db.session() as con:
        text = costs.template(con)
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=cost_template.csv"},
    )


@app.post("/api/actions/{action_id}/ack")
def ack(action_id: str, body: AckRequest) -> dict[str, str]:
    with db.session() as con:
        con.execute(
            "INSERT INTO ops.action_ack VALUES (?, ?, ?, now())",
            [action_id, body.status, body.note],
        )
    return {"status": "ok"}


@app.get("/api/v1/semantic/catalogue")
def semantic_catalogue() -> dict:
    return semantic.catalogue()


@app.get("/api/v1/trend")
def trend(
    start: dt.date | None = Query(None),
    end: dt.date | None = Query(None),
    granularity: str = Query("day"),
) -> dict:
    with db.session() as con:
        resolved_start, resolved_end = analysis._period(con, start, end)
        try:
            return analysis.trend(con, resolved_start, resolved_end, granularity)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/history")
def history(limit: int = Query(20, ge=1, le=100)) -> dict:
    with db.session() as con:
        runs = con.execute(
            "SELECT id, snapshot_id, kind, question, intent, created_at "
            "FROM ops.analysis_run ORDER BY id DESC LIMIT ?",
            [limit],
        ).fetchall()
        actions = con.execute(
            "SELECT action_id, status, note, updated_at "
            "FROM ops.action_ack ORDER BY updated_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    return {
        "runs": [
            {
                "id": row[0],
                "snapshot_id": row[1],
                "kind": row[2],
                "question": row[3],
                "intent": row[4],
                "created_at": row[5].isoformat() if hasattr(row[5], "isoformat") else row[5],
            }
            for row in runs
        ],
        "actions": [
            {
                "action_id": row[0],
                "status": row[1],
                "note": row[2],
                "updated_at": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3],
            }
            for row in actions
        ],
    }


@app.get("/api/v1/evidence/{run_id}")
def evidence(run_id: int) -> dict:
    with db.session() as con:
        row = con.execute(
            "SELECT result_json FROM ops.analysis_run WHERE id = ?", [run_id]
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="没有这次分析记录")
    return json.loads(row[0])


@app.get("/api/v1/datasets")
def dataset_registry() -> dict:
    with db.session() as con:
        rows = con.execute(
            "SELECT dataset, source, rows, latest, imported_at, note "
            "FROM ops.dataset_registry ORDER BY dataset"
        ).fetchall()
    return {
        "datasets": [
            {
                "dataset": row[0],
                "source": row[1],
                "rows": int(row[2]),
                "latest": row[3],
                "imported_at": row[4].isoformat() if hasattr(row[4], "isoformat") else row[4],
                "note": row[5],
            }
            for row in rows
        ]
    }


@app.get("/api/v1/ask/stream")
def ask_stream(
    question: str = Query(..., min_length=1, max_length=500),
    start: dt.date | None = Query(None),
    end: dt.date | None = Query(None),
) -> StreamingResponse:
    def events():
        yield "event: started\ndata: {}\n\n"
        try:
            with db.session() as con:
                result = llm.answer_question(con, question, start, end)
                db.record_analysis(
                    con,
                    kind="ask",
                    question=question,
                    intent=result["intent"],
                    result=result,
                )
            yield "event: result\ndata: " + json.dumps(
                result, ensure_ascii=False, default=str
            ) + "\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:  # noqa: BLE001 - the stream must still end
            _log.exception("ask stream failed")
            yield "event: error\ndata: " + json.dumps(
                {"message": str(exc)[:200]}, ensure_ascii=False
            ) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/v1/ops/health")
def ops_health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/ops/version")
def ops_version() -> dict:
    return {"version": ops.VERSION, "metric_version": semantic.VERSION}


@app.get("/api/v1/ops/status")
def ops_status() -> dict:
    return ops.status()


@app.post("/api/v1/ops/backup")
def ops_backup() -> dict:
    return ops.backup()


@app.get("/api/v1/ops/diagnostics")
def ops_diagnostics() -> Response:
    payload = ops.diagnostics()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=lira-diagnostics.zip"
        },
    )


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: str = Field(min_length=1, max_length=80)
    payload: dict[str, str] = Field(default_factory=dict)


@app.post("/api/v1/ops/telemetry")
def telemetry(body: TelemetryEvent) -> dict:
    with db.session() as con:
        con.execute(
            "INSERT INTO ops.telemetry VALUES (now(), ?, ?)",
            [body.event, json.dumps(body.payload, ensure_ascii=False)],
        )
    return {"status": "ok"}


_V1_ALIASES = (
    ("/api/v1/overview", overview, ["GET"]),
    ("/api/v1/loss-skus", loss_skus, ["GET"]),
    ("/api/v1/ad-waste", ad_waste, ["GET"]),
    ("/api/v1/skus/{sku}", sku_detail, ["GET"]),
    ("/api/v1/data-health", data_health, ["GET"]),
    ("/api/v1/sync", sync, ["POST"]),
    ("/api/v1/import/preview", import_preview, ["POST"]),
    ("/api/v1/import/confirm", import_confirm, ["POST"]),
    ("/api/v1/import/scan", import_scan, ["POST"]),
    ("/api/v1/import/status", import_status, ["GET"]),
    ("/api/v1/sku-aliases", sku_aliases, ["GET"]),
    ("/api/v1/sku-aliases", sku_alias_upsert, ["POST"]),
    ("/api/v1/sku-aliases/{platform_sku}", sku_alias_delete, ["DELETE"]),
    ("/api/v1/connectors", connector_status, ["GET"]),
    ("/api/v1/connectors/{name}/configure", connector_configure, ["POST"]),
    ("/api/v1/connectors/{name}/test", connector_test, ["POST"]),
    ("/api/v1/connectors/{name}", connector_delete, ["DELETE"]),
    ("/api/v1/costs/preview", cost_preview, ["POST"]),
    ("/api/v1/costs/confirm", cost_confirm, ["POST"]),
    ("/api/v1/costs/template", cost_template, ["GET"]),
    ("/api/v1/actions/{action_id}/ack", ack, ["POST"]),
    ("/api/v1/ask", ask, ["POST"]),
)
for _path, _endpoint, _methods in _V1_ALIASES:
    app.add_api_route(_path, _endpoint, methods=_methods)


@app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def client_shell(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="没有这个接口")
    candidate = STATIC / path
    if path and candidate.is_file() and candidate.resolve().is_relative_to(STATIC.resolve()):
        return FileResponse(candidate)
    return FileResponse(STATIC / "index.html")


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("LIRA_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("LIRA_API_PORT", "8010")),
    )


if __name__ == "__main__":
    main()
