from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

os.environ["LIRA_DISABLE_WATCH"] = "1"

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import connectors, erp, imports, top
from app.main import app
import app.main as app_main


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        assert test_client.post("/api/demo/reset").status_code == 200
        yield test_client


def test_overview(client):
    response = client.get("/api/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["net_revenue"] > 0
    assert data["loss_sku_count"] >= 1
    assert data["cost_coverage"] is not None
    assert data["cost_coverage"] < 1
    assert data["ad_waste_total"] > 0
    assert len(data["actions"]) >= 1
    assert len(data["profit_bridge"]) == 7


def test_loss_skus(client):
    response = client.get("/api/loss-skus")
    assert response.status_code == 200
    data = response.json()
    assert data["items"]
    assert all(item["contribution_margin"] < 0 for item in data["items"])


def test_ad_waste(client):
    response = client.get("/api/ad-waste")
    assert response.status_code == 200
    data = response.json()
    assert data["total_waste"] > 0
    assert any(item["waste"] > 0 for item in data["items"])


def test_sku_detail(client):
    response = client.get("/api/skus/A001")
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "A001"
    assert len(data["profit_bridge"]) == 7
    assert data["contribution_margin"] < 0
    assert data["evidence"]["costs"] >= 1


def test_missing_sku_is_404(client):
    assert client.get("/api/skus/NOPE").status_code == 404


def test_ack(client):
    response = client.post(
        "/api/actions/loss:A001/ack", json={"status": "adopted"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health(client):
    response = client.get("/api/data-health")
    assert response.status_code == 200
    data = response.json()
    assert data["sources"]
    assert "X999" in data["missing_skus"]


def test_cost_template(client):
    response = client.get("/api/costs/template")
    assert response.status_code == 200
    assert "商品编码" in response.text


def test_cost_preview_and_confirm(client):
    csv_text = "商品编码,生效日期,采购单价,运费,包材\nX999,2026-08-01,30,4,1.5\n"
    preview = client.post(
        "/api/costs/preview",
        files={"file": ("costs.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200
    data = preview.json()
    assert data["row_count"] == 1
    assert data["suggested"]["sku"] == "商品编码"
    assert data["suggested"]["effective_from"] == "生效日期"
    assert data["suggested"]["unit_cost"] == "采购单价"

    confirm = client.post(
        "/api/costs/confirm",
        json={
            "upload_id": data["upload_id"],
            "mapping": {
                "sku": "商品编码",
                "effective_from": "生效日期",
                "unit_cost": "采购单价",
                "shipping_cost": "运费",
                "packaging_cost": "包材",
            },
        },
    )
    assert confirm.status_code == 200
    result = confirm.json()
    assert result["imported"] == 1
    assert result["cost_coverage"] == 1.0
    assert result["missing_skus"] == []

    health = client.get("/api/data-health").json()
    assert "X999" not in health["missing_skus"]

    assert client.post("/api/demo/reset").status_code == 200


def test_alias_and_order_import(client):
    response = client.post(
        "/api/sku-aliases",
        json={"platform_sku": "P-A001", "merchant_sku": "A001"},
    )
    assert response.status_code == 200

    csv_text = (
        "order_line_id,order_id,sku,quantity,paid_amount,order_date\n"
        "T-ALIAS-1,T-ALIAS-1,P-A001,1,59,2026-10-01\n"
    )
    preview = client.post(
        "/api/import/preview?dataset=orders",
        files={"file": ("orders_alias.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200
    data = preview.json()
    assert data["suggested"]["sku"] == "sku"
    assert data["targets"]

    confirm = client.post(
        "/api/import/confirm",
        json={
            "dataset": "orders",
            "upload_id": data["upload_id"],
            "mapping": {
                "order_line_id": "order_line_id",
                "order_id": "order_id",
                "sku": "sku",
                "quantity": "quantity",
                "paid_amount": "paid_amount",
                "order_date": "order_date",
            },
            "replace": False,
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["imported"] == 1

    aliases = client.get("/api/sku-aliases").json()
    assert "P-A001" not in aliases["unresolved"]

    assert client.delete("/api/sku-aliases/P-A001").status_code == 200
    assert client.post("/api/demo/reset").status_code == 200


def test_real_taobao_export_shape(client):
    csv_text = (
        "订单编号,订单状态,订单创建时间,宝贝标题,购买数量,宝贝单价,买家实际支付金额\n"
        "T-TAOBAO-1,交易成功,2026-10-01 10:00:00,【纯棉】基础款短袖 男 款A001,1,59.00,59.00\n"
    )
    preview = client.post(
        "/api/import/preview?dataset=orders",
        files={"file": ("taobao_gbk.csv", csv_text.encode("gbk"), "text/csv")},
    )
    assert preview.status_code == 200
    data = preview.json()
    assert data["suggested"]["sku"] == "宝贝标题"
    assert data["suggested"]["order_date"] == "订单创建时间"
    confirm = client.post(
        "/api/import/confirm",
        json={
            "dataset": "orders",
            "upload_id": data["upload_id"],
            "mapping": {
                "order_line_id": "订单编号",
                "order_id": "订单编号",
                "sku": "宝贝标题",
                "quantity": "购买数量",
                "paid_amount": "买家实际支付金额",
                "order_date": "订单创建时间",
                "status": "订单状态",
            },
            "replace": False,
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["imported"] == 1
    assert client.post("/api/demo/reset").status_code == 200


def test_refund_and_ad_import(client):
    refund_csv = (
        "refund_id,order_line_id,amount,reason,refund_date\n"
        "R-UI-1,T-ALIAS-1,10,尺码,2026-10-02\n"
    )
    preview = client.post(
        "/api/import/preview?dataset=refunds",
        files={"file": ("refunds_ui.csv", refund_csv.encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200
    refund_preview = preview.json()
    confirm = client.post(
        "/api/import/confirm",
        json={
            "dataset": "refunds",
            "upload_id": refund_preview["upload_id"],
            "mapping": {
                "refund_id": "refund_id",
                "order_line_id": "order_line_id",
                "amount": "amount",
                "reason": "reason",
                "refund_date": "refund_date",
            },
            "replace": False,
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["imported"] == 1

    ad_csv = (
        "ad_date,campaign,sku,spend,attributed_revenue\n"
        "2026-10-01,计划UI,A001,10,20\n"
    )
    preview = client.post(
        "/api/import/preview?dataset=ads",
        files={"file": ("ads_ui.csv", ad_csv.encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200
    ad_preview = preview.json()
    confirm = client.post(
        "/api/import/confirm",
        json={
            "dataset": "ads",
            "upload_id": ad_preview["upload_id"],
            "mapping": {
                "ad_date": "ad_date",
                "campaign": "campaign",
                "sku": "sku",
                "spend": "spend",
                "attributed_revenue": "attributed_revenue",
            },
            "replace": False,
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["imported"] == 1

    assert client.post("/api/demo/reset").status_code == 200


def test_import_scan(client):
    imports.ensure_inbox()
    name = f"orders_scan_{uuid.uuid4().hex}.csv"
    path = imports.INBOX / name
    path.write_text(
        "order_line_id,order_id,sku,quantity,paid_amount,order_date\n"
        "T-SCAN-1,T-SCAN-1,A001,1,59,2026-10-01\n",
        encoding="utf-8",
    )
    response = client.post("/api/import/scan")
    assert response.status_code == 200
    body = response.json()
    assert any(item.get("file") == name and item.get("status") == "ok" for item in body["scanned"])
    assert client.post("/api/demo/reset").status_code == 200


def test_import_status(client):
    response = client.get("/api/import/status")
    assert response.status_code == 200
    data = response.json()
    assert "inbox" in data
    assert "interval_s" in data
    assert "watcher" in data
    assert "model" in data


def test_pii_scrub():
    cleaned = connectors.scrub_order(
        {
            "order_line_id": "L1",
            "order_id": "O1",
            "sku": "A001",
            "quantity": 1,
            "paid_amount": 59,
            "order_date": "2026-10-01",
            "status": "已完成",
            "buyer_name": "张三",
            "buyer_phone": "13800000000",
            "address": "某省某市",
            "member_id": "member-1",
        }
    )
    assert "buyer_name" not in cleaned
    assert "buyer_phone" not in cleaned
    assert "address" not in cleaned
    assert cleaned["member_id_hash"].startswith("sha256:")
    assert cleaned["sku"] == "A001"


def test_token_store_is_encrypted(tmp_path):
    store = connectors.TokenStore(tmp_path / "tokens.enc")
    store.set(
        "taobao",
        {
            "app_key": "key-value",
            "app_secret": "very-secret-value",
            "session": "session-value",
        },
    )
    assert store.get("taobao")["app_key"] == "key-value"
    raw = (tmp_path / "tokens.enc").read_bytes()
    assert b"very-secret-value" not in raw
    assert b"session-value" not in raw
    store.delete("taobao")
    assert store.names() == []


def test_eval_set_shape():
    path = Path(__file__).resolve().parent / "eval" / "questions.json"
    questions = json.loads(path.read_text(encoding="utf-8"))
    assert len(questions) >= 100
    assert {item["expected_intent"] for item in questions} == {
        "sku", "loss", "ad", "overview",
    }
    assert all(item["question"] and item["require_any"] for item in questions)


def test_top_signing():
    params = {
        "method": "taobao.time.get",
        "app_key": "key",
        "timestamp": "2026-10-01 00:00:00",
    }
    expected = hashlib.md5(
        ("secret" + "".join(f"{key}{params[key]}" for key in sorted(params)) + "secret").encode()
    ).hexdigest().upper()
    assert top.sign(params, "secret") == expected
    with pytest.raises(top.TopNotConfigured):
        top.time_get("", "")


def test_quota():
    quota = connectors.Quota(per_minute=1)
    assert quota.consume("taobao") is True
    assert quota.consume("taobao") is False
    assert quota.remaining("taobao") == 0


def test_connectors_api(client):
    status = client.get("/api/connectors")
    assert status.status_code == 200
    data = status.json()
    assert "folder" in data
    assert "taobao" in data
    assert "pii" in data

    configured = client.post(
        "/api/connectors/taobao/configure",
        json={
            "app_key": "key-value",
            "app_secret": "very-secret-value",
            "session": "session-value",
        },
    )
    assert configured.status_code == 200
    assert configured.json()["taobao"]["configured"] is True
    assert "very-secret-value" not in json.dumps(configured.json())

    tested = client.post("/api/connectors/taobao/test")
    assert tested.status_code == 200
    assert tested.json()["ok"] is True

    deleted = client.delete("/api/connectors/taobao")
    assert deleted.status_code == 200
    assert deleted.json()["taobao"]["configured"] is False


def test_v1_overview_contract(client):
    response = client.get("/api/v1/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot_id"] > 0
    assert data["metric_version"]
    assert data["order_count"] >= 1
    assert data["aov"] is not None
    assert len(data["comparisons"]) == 4
    assert "evidence" in data
    assert isinstance(data["categories"], list)


def test_catalogue(client):
    response = client.get("/api/v1/semantic/catalogue")
    assert response.status_code == 200
    data = response.json()
    assert data["version"]
    assert any(metric["name"] == "gross_margin" for metric in data["metrics"])
    assert any(dimension["name"] == "sku" for dimension in data["dimensions"])


def test_trend(client):
    response = client.get("/api/v1/trend?granularity=day")
    assert response.status_code == 200
    data = response.json()
    assert data["rows"]
    assert data["snapshot_id"] > 0
    assert "net_revenue" in data["rows"][0]


def test_history_and_evidence(client):
    history = client.get("/api/v1/history").json()
    assert history["runs"]
    run_id = history["runs"][0]["id"]
    evidence = client.get(f"/api/v1/evidence/{run_id}")
    assert evidence.status_code == 200
    assert "period" in evidence.json()
    assert client.get("/api/v1/evidence/999999").status_code == 404


def test_error_envelope(client):
    response = client.get("/api/v1/skus/NOPE")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"]


def test_gbk_and_xlsx_preview(client):
    gbk = "商品编码,生效日期,采购单价\nX999,2026-08-01,30\n".encode("gbk")
    response = client.post(
        "/api/costs/preview",
        files={"file": ("costs_gbk.csv", gbk, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["suggested"]["sku"] == "商品编码"

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["商品编码", "生效日期", "采购单价"])
    sheet.append(["X999", "2026-08-01", 30])
    buffer = BytesIO()
    workbook.save(buffer)
    response = client.post(
        "/api/costs/preview",
        files={
            "file": (
                "costs.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["row_count"] == 1


def test_snapshot_moves_after_import(client):
    before = client.get("/api/v1/overview").json()["snapshot_id"]
    csv_text = "商品编码,生效日期,采购单价,运费,包材\nX999,2026-08-01,30,4,1.5\n"
    preview = client.post(
        "/api/costs/preview",
        files={"file": ("costs.csv", csv_text.encode("utf-8"), "text/csv")},
    ).json()
    confirm = client.post(
        "/api/costs/confirm",
        json={
            "upload_id": preview["upload_id"],
            "mapping": {
                "sku": "商品编码",
                "effective_from": "生效日期",
                "unit_cost": "采购单价",
                "shipping_cost": "运费",
                "packaging_cost": "包材",
            },
        },
    )
    assert confirm.status_code == 200
    after = client.get("/api/v1/overview").json()["snapshot_id"]
    assert after > before
    assert client.post("/api/demo/reset").status_code == 200


def test_datasets_registry(client):
    response = client.get("/api/v1/datasets")
    assert response.status_code == 200
    assert isinstance(response.json()["datasets"], list)


def test_ops_endpoints(client):
    status = client.get("/api/v1/ops/status")
    assert status.status_code == 200
    assert status.json()["version"]
    assert status.json()["snapshot_id"] > 0

    backup = client.post("/api/v1/ops/backup")
    assert backup.status_code == 200
    assert backup.json()["bytes"] > 0

    diagnostics = client.get("/api/v1/ops/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.content.startswith(b"PK")

    assert client.get("/api/v1/ops/version").json()["version"]


class _MockTop(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        params = {
            key: values[0]
            for key, values in urllib.parse.parse_qs(
                self.rfile.read(length).decode("utf-8")
            ).items()
        }
        if params.get("method") == "taobao.time.get":
            body = {"time_get_response": {"time": "2026-10-01 00:00:00"}}
        else:
            body = {
                "trades_sold_get_response": {
                    "trades": {
                        "trade": [
                            {
                                "tid": "T-MOCK-1",
                                "status": "TRADE_FINISHED",
                                "created": "2026-10-01 10:00:00",
                                "orders": {
                                    "order": [
                                        {
                                            "oid": "L1",
                                            "num": "1",
                                            "price": "59",
                                            "total_fee": "59",
                                            "outer_iid": "A001",
                                        }
                                    ]
                                },
                            }
                        ]
                    },
                    "has_next": False,
                }
            }
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class _MockErp(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/health"):
            body = {"ok": True}
        else:
            body = {
                "orders": [
                    {
                        "order_line_id": "E-MOCK-1",
                        "order_id": "E-MOCK-1",
                        "sku": "A001",
                        "quantity": 1,
                        "paid_amount": 59,
                        "order_date": "2026-10-01",
                        "status": "已完成",
                    }
                ]
            }
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_top_pull_with_mock(client, monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockTop)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        top, "BASE_URL", f"http://127.0.0.1:{server.server_port}/router/rest"
    )
    try:
        configured = client.post(
            "/api/v1/connectors/taobao/configure",
            json={"app_key": "key", "app_secret": "secret", "session": "session"},
        )
        assert configured.status_code == 200
        pulled = client.post(
            "/api/v1/connectors/taobao/pull?start=2026-10-01&end=2026-10-31"
        )
        assert pulled.status_code == 200
        assert pulled.json()["imported"] >= 1
    finally:
        client.delete("/api/v1/connectors/taobao")
        client.post("/api/demo/reset")
        server.shutdown()
        server.server_close()


def test_erp_pull_with_mock(client):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockErp)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        configured = client.post(
            "/api/v1/connectors/erp/configure",
            json={
                "base_url": f"http://127.0.0.1:{server.server_port}",
                "token": "token",
            },
        )
        assert configured.status_code == 200
        pulled = client.post(
            "/api/v1/connectors/erp/pull?start=2026-10-01&end=2026-10-31"
        )
        assert pulled.status_code == 200
        assert pulled.json()["imported"] >= 1
    finally:
        client.delete("/api/v1/connectors/erp")
        client.post("/api/demo/reset")
        server.shutdown()
        server.server_close()


def test_pin_guard(client):
    original = app_main._PIN
    app_main._PIN = "2468"
    try:
        unauthorized = client.get("/api/v1/overview")
        assert unauthorized.status_code == 401
        authorized = client.get(
            "/api/v1/overview", headers={"X-Lira-Pin": "2468"}
        )
        assert authorized.status_code == 200
    finally:
        app_main._PIN = original


def test_ask(client):
    response = client.post("/api/ask", json={"question": "哪些商品在亏钱"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"]
    assert data["intent"] in ("loss", "sku", "ad", "overview")
    assert "evidence" in data


def test_demo_reset(client):
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert response.json()["orders"] > 0


def test_sync(client):
    response = client.post("/api/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["orders"] > 0
    assert data["costs"] > 0
