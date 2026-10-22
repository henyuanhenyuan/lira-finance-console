"""DuckDB warehouse: load the raw files, build the line and ad views."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import duckdb

from .seed import SAMPLE, ensure_sample

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = DATA / "lira.duckdb"

_LOCK = threading.Lock()

_RAW = (
    ("orders", "orders.csv"),
    ("refunds", "refunds.csv"),
    ("ads", "ads.csv"),
    ("costs", "costs.csv"),
    ("skus", "skus.csv"),
    ("fees", "fees.csv"),
)


def _connect() -> duckdb.DuckDBPyConnection:
    DATA.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("SET TimeZone='Asia/Shanghai'")
    return con


@contextmanager
def session() -> Iterator[duckdb.DuckDBPyConnection]:
    with _LOCK:
        con = _connect()
        try:
            yield con
        finally:
            con.close()


def _table_exists(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    return bool(
        con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()[0]
    )


def _load_raw(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("CREATE SCHEMA IF NOT EXISTS lake")
    con.execute("CREATE SCHEMA IF NOT EXISTS ops")
    con.execute("DROP VIEW IF EXISTS lake.lines")
    con.execute("DROP VIEW IF EXISTS lake.ad_lines")

    for table, filename in _RAW:
        path = (SAMPLE / filename).as_posix()
        con.execute(
            f"CREATE OR REPLACE TABLE raw.{table} AS "
            f"SELECT * FROM read_csv_auto('{path}')"
        )

    con.execute(
        "CREATE TABLE IF NOT EXISTS ops.sync_run ("
        " synced_at TIMESTAMP, orders BIGINT, refunds BIGINT, ads BIGINT, costs BIGINT)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ops.action_ack ("
        " action_id VARCHAR, status VARCHAR, note VARCHAR, updated_at TIMESTAMP)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ops.import_log ("
        " imported_at TIMESTAMP, dataset VARCHAR, filename VARCHAR,"
        " imported BIGINT, skipped BIGINT, status VARCHAR, error VARCHAR)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS raw.sku_alias ("
        " platform_sku_id VARCHAR, merchant_sku VARCHAR, updated_at TIMESTAMP)"
    )
    _ensure_ops(con)
    con.execute(
        "INSERT INTO ops.sync_run SELECT now(), "
        "(SELECT count(*) FROM raw.orders), "
        "(SELECT count(*) FROM raw.refunds), "
        "(SELECT count(*) FROM raw.ads), "
        "(SELECT count(*) FROM raw.costs)"
    )
    _create_views(con)
    bump_snapshot(con, "load")


def _create_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE VIEW lake.lines AS
        WITH refunds AS (
            SELECT order_line_id, SUM(amount) AS refund_amount
            FROM raw.refunds
            GROUP BY order_line_id
        ),
        base AS (
            SELECT
                o.order_line_id,
                o.order_id,
                o.sku,
                o.order_date,
                o.quantity,
                o.paid_amount,
                COALESCE(r.refund_amount, 0) AS refund_amount,
                o.paid_amount - COALESCE(r.refund_amount, 0) AS net_revenue,
                s.title,
                s.category,
                s.supplier,
                a.merchant_sku,
                COALESCE(a.merchant_sku, o.sku) AS cost_sku,
                f.commission_rate,
                f.payment_fee_rate
            FROM raw.orders AS o
            LEFT JOIN refunds AS r ON r.order_line_id = o.order_line_id
            LEFT JOIN raw.skus AS s ON s.sku = o.sku
            LEFT JOIN raw.sku_alias AS a ON a.platform_sku_id = o.sku
            LEFT JOIN raw.fees AS f ON f.category = s.category
        )
        SELECT
            b.order_line_id,
            b.order_id,
            b.sku,
            b.order_date,
            b.quantity,
            b.paid_amount,
            b.refund_amount,
            b.net_revenue,
            b.title,
            b.category,
            b.supplier,
            b.merchant_sku,
            b.cost_sku,
            c.unit_cost,
            c.shipping_cost,
            c.packaging_cost,
            CASE WHEN c.unit_cost IS NULL THEN NULL
                 ELSE b.quantity * c.unit_cost END AS goods_cost,
            CASE WHEN c.unit_cost IS NULL THEN NULL
                 ELSE b.quantity * (c.shipping_cost + c.packaging_cost) END AS fulfillment_cost,
            CASE WHEN b.commission_rate IS NULL THEN NULL
                 ELSE b.net_revenue * b.commission_rate
                      + b.paid_amount * b.payment_fee_rate END AS platform_fee
        FROM base AS b
        ASOF LEFT JOIN raw.costs AS c
            ON c.sku = b.cost_sku AND b.order_date >= c.effective_from
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW lake.ad_lines AS
        SELECT ad_date, campaign, sku, spend, attributed_revenue
        FROM raw.ads
        """
    )


def _ensure_ops(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS ops")
    con.execute(
        "CREATE TABLE IF NOT EXISTS ops.snapshot ("
        " id BIGINT, created_at TIMESTAMP, note VARCHAR)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ops.analysis_run ("
        " id BIGINT, snapshot_id BIGINT, kind VARCHAR, question VARCHAR,"
        " intent VARCHAR, result_json VARCHAR, created_at TIMESTAMP)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ops.dataset_registry ("
        " dataset VARCHAR, source VARCHAR, rows BIGINT, latest VARCHAR,"
        " imported_at TIMESTAMP, note VARCHAR)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ops.telemetry ("
        " recorded_at TIMESTAMP, event VARCHAR, payload VARCHAR)"
    )


def snapshot_id(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute("SELECT max(id) FROM ops.snapshot").fetchone()
    return int(row[0] or 0)


def bump_snapshot(con: duckdb.DuckDBPyConnection, note: str) -> int:
    next_id = snapshot_id(con) + 1
    con.execute(
        "INSERT INTO ops.snapshot VALUES (?, now(), ?)", [next_id, note]
    )
    return next_id


def record_analysis(
    con: duckdb.DuckDBPyConnection,
    *,
    kind: str,
    question: str,
    intent: str,
    result: dict[str, Any],
) -> int:
    next_id = int(
        con.execute("SELECT COALESCE(max(id), 0) + 1 FROM ops.analysis_run").fetchone()[0]
    )
    con.execute(
        "INSERT INTO ops.analysis_run VALUES (?, ?, ?, ?, ?, ?, now())",
        [
            next_id,
            snapshot_id(con),
            kind,
            question,
            intent,
            json.dumps(result, ensure_ascii=False, default=str),
        ],
    )
    return next_id


def record_dataset(
    con: duckdb.DuckDBPyConnection,
    *,
    dataset: str,
    source: str,
    rows: int,
    latest: str,
    note: str = "",
) -> None:
    con.execute("DELETE FROM ops.dataset_registry WHERE dataset = ?", [dataset])
    con.execute(
        "INSERT INTO ops.dataset_registry VALUES (?, ?, ?, ?, now(), ?)",
        [dataset, source, int(rows), latest, note],
    )


def ensure_db() -> None:
    ensure_sample()
    with session() as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS ops")
        con.execute(
            "CREATE TABLE IF NOT EXISTS ops.sync_run ("
            " synced_at TIMESTAMP, orders BIGINT, refunds BIGINT, ads BIGINT, costs BIGINT)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS ops.action_ack ("
            " action_id VARCHAR, status VARCHAR, note VARCHAR, updated_at TIMESTAMP)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS ops.import_log ("
            " imported_at TIMESTAMP, dataset VARCHAR, filename VARCHAR,"
            " imported BIGINT, skipped BIGINT, status VARCHAR, error VARCHAR)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS raw.sku_alias ("
            " platform_sku_id VARCHAR, merchant_sku VARCHAR, updated_at TIMESTAMP)"
        )
        _ensure_ops(con)
        if not _table_exists(con, "raw", "orders"):
            _load_raw(con)


def _counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts = {
        "orders": con.execute("SELECT count(*) FROM raw.orders").fetchone()[0],
        "refunds": con.execute("SELECT count(*) FROM raw.refunds").fetchone()[0],
        "ads": con.execute("SELECT count(*) FROM raw.ads").fetchone()[0],
        "costs": con.execute("SELECT count(*) FROM raw.costs").fetchone()[0],
    }
    return {name: int(value) for name, value in counts.items()}


def refresh_views(con: duckdb.DuckDBPyConnection) -> None:
    _create_views(con)


def reset_sample() -> dict[str, int]:
    """Restore the deterministic sample. A demo action, not a sync."""
    ensure_sample(force=True)
    with session() as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute(
            "CREATE TABLE IF NOT EXISTS raw.sku_alias ("
            " platform_sku_id VARCHAR, merchant_sku VARCHAR, updated_at TIMESTAMP)"
        )
        con.execute("DELETE FROM raw.sku_alias")
        _load_raw(con)
        return _counts(con)


def reload() -> dict[str, int]:
    """Rebuild the views from whatever is in raw, and record the run."""
    with session() as con:
        _create_views(con)
        con.execute(
            "INSERT INTO ops.sync_run SELECT now(), "
            "(SELECT count(*) FROM raw.orders), "
            "(SELECT count(*) FROM raw.refunds), "
            "(SELECT count(*) FROM raw.ads), "
            "(SELECT count(*) FROM raw.costs)"
        )
        bump_snapshot(con, "reload")
        return _counts(con)
