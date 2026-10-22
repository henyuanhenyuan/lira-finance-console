"""Credential, quota and PII boundaries for connectors.

No TOP/ERP request is made here: both need an app key, merchant authorization
and a verified session. What this module owns is the boundary those adapters
will sit behind — secrets encrypted at rest, a visible quota, and an order
scrubber that drops buyer identifiers before data enters the warehouse.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from . import erp, imports, top

ROOT = Path(__file__).resolve().parents[1]
SECRET_DIR = Path(os.environ.get("LIRA_SECRET_DIR", ROOT / "data" / "secrets"))
TOKENS = SECRET_DIR / "connectors.enc"
KEY = SECRET_DIR / "master.key"
LOG_DIR = ROOT / "data" / "logs"

_LOCK = threading.Lock()

_PII_KEYS = {
    "buyer_name", "buyer_phone", "buyer_mobile", "receiver_name", "receiver_phone",
    "address", "shipping_address", "mobile", "phone", "email", "id_card", "buyer_email",
}
_SAFE_ORDER = (
    "order_line_id", "order_id", "sku", "quantity", "paid_amount", "order_date",
    "status", "region",
)


def _log(event: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "connector.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {event}\n")
    except OSError:
        pass


def _fernet(key_path: Path) -> Fernet:
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
    return Fernet(key_path.read_bytes())


class TokenStore:
    """Encrypted JSON store. Secrets never leave this class through status()."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or TOKENS
        self.key_path = (self.path.parent / "master.key") if path is not None else KEY

    def _read(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            payload = _fernet(self.key_path).decrypt(self.path.read_bytes())
            data = json.loads(payload.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (InvalidToken, json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(
            _fernet(self.key_path).encrypt(
                json.dumps(data, ensure_ascii=False).encode("utf-8")
            )
        )

    def set(self, name: str, payload: dict[str, str]) -> None:
        with _LOCK:
            data = self._read()
            data[name] = {
                key: str(value)
                for key, value in payload.items()
                if value is not None and str(value).strip()
            }
            data[name]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._write(data)
        _log(f"configure {name}")

    def get(self, name: str) -> dict[str, str] | None:
        with _LOCK:
            return self._read().get(name)

    def delete(self, name: str) -> None:
        with _LOCK:
            data = self._read()
            data.pop(name, None)
            self._write(data)
        _log(f"delete {name}")

    def names(self) -> list[str]:
        with _LOCK:
            return sorted(self._read())


class Quota:
    """A local, per-process rate limit. Persistence is not the point here."""

    def __init__(self, per_minute: int | None = None) -> None:
        self.per_minute = per_minute or int(os.environ.get("LIRA_QUOTA_PER_MINUTE", "60"))
        self._calls: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def consume(self, name: str) -> bool:
        now = time.time()
        with self._lock:
            calls = [stamp for stamp in self._calls.get(name, []) if now - stamp < 60]
            if len(calls) >= self.per_minute:
                self._calls[name] = calls
                return False
            calls.append(now)
            self._calls[name] = calls
            return True

    def remaining(self, name: str) -> int:
        now = time.time()
        with self._lock:
            calls = [stamp for stamp in self._calls.get(name, []) if now - stamp < 60]
            self._calls[name] = calls
            return max(0, self.per_minute - len(calls))

    def status(self) -> dict[str, int]:
        return {name: self.remaining(name) for name in ("taobao", "erp", "folder")}


STORE = TokenStore()
QUOTA = Quota()

PII_POLICY = (
    "订单只保留经营字段；买家姓名、电话、地址、身份证等字段在进入仓库前丢弃；"
    "买家标识只保留截断哈希。"
)


def scrub_order(record: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: record[key] for key in _SAFE_ORDER if key in record}
    for key in list(cleaned):
        if key in _PII_KEYS:
            cleaned.pop(key, None)
    member = record.get("member_id") or record.get("buyer_id")
    if member:
        cleaned["member_id_hash"] = (
            "sha256:" + hashlib.sha256(str(member).encode("utf-8")).hexdigest()[:16]
        )
    return cleaned


def status() -> dict[str, Any]:
    names = STORE.names()
    return {
        "folder": {
            "configured": True,
            "inbox": str(imports.INBOX),
            "mode": "event+poll",
        },
        "taobao": {
            "configured": "taobao" in names,
            "message": "需要 app key、app secret、商家 session；真实接口调用需要授权验证。",
        },
        "erp": {
            "configured": "erp" in names,
            "message": "需要 ERP 地址与 token；具体接口由 ERP 厂商提供。",
        },
        "pii": {"policy": PII_POLICY},
        "quota": {"per_minute": QUOTA.per_minute, "remaining": QUOTA.status()},
    }


def configure(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name not in {"taobao", "erp"}:
        raise ValueError("只支持 taobao 或 erp")
    required = (
        ("app_key", "app_secret", "session") if name == "taobao" else ("base_url", "token")
    )
    missing = [key for key in required if not str(payload.get(key, "")).strip()]
    if missing:
        raise ValueError("缺少凭证字段：" + "、".join(missing))
    STORE.set(name, {key: str(payload[key]) for key in required})
    return status()


def delete(name: str) -> dict[str, Any]:
    if name not in {"taobao", "erp"}:
        raise ValueError("只支持 taobao 或 erp")
    STORE.delete(name)
    return status()


def pull(name: str, start: str, end: str) -> dict[str, Any]:
    """Pull orders from a configured connector and run them through the inbox.

    The connector only fetches; ingestion, mapping and warehouse writes stay in
    the same import pipeline as a file drop.
    """
    credentials = STORE.get(name)
    if credentials is None:
        raise ValueError("未配置凭证")

    if name == "taobao":
        rows = top.TopClient(
            credentials.get("app_key", ""),
            credentials.get("app_secret", ""),
            credentials.get("session", ""),
        ).pull_orders(start, end)
    elif name == "erp":
        rows = erp.ErpClient(
            credentials.get("base_url", ""), credentials.get("token", "")
        ).pull_orders(start, end)
    else:
        raise ValueError("只支持 taobao 或 erp")

    if not rows:
        return {"rows": 0, "imported": 0, "scanned": []}

    imports.ensure_inbox()
    path = imports.INBOX / f"orders_{name}_{int(time.time())}.csv"
    columns = [
        "order_line_id", "order_id", "sku", "quantity",
        "paid_amount", "order_date", "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    results = imports.scan_inbox()
    imported = sum(
        int(item.get("imported", 0))
        for item in results
        if item.get("file") == path.name and item.get("status") == "ok"
    )
    return {"rows": len(rows), "imported": imported, "scanned": results}


def test(name: str) -> dict[str, Any]:
    if name == "folder":
        return {"ok": True, "message": f"收件箱：{imports.INBOX}"}
    if name not in {"taobao", "erp"}:
        return {"ok": False, "message": "未知连接器"}
    credentials = STORE.get(name)
    if credentials is None:
        return {"ok": False, "message": "未配置凭证"}

    if name == "taobao" and os.environ.get("LIRA_TOP_LIVE") == "1":
        try:
            top.time_get(
                credentials.get("app_key", ""),
                credentials.get("app_secret", ""),
                credentials.get("session", ""),
            )
            return {"ok": True, "message": "TOP 签名与时间接口校验通过。"}
        except top.TopError as exc:
            return {"ok": False, "message": f"TOP 校验失败：{exc}"}

    return {
        "ok": True,
        "message": "凭证已加密保存；设置 LIRA_TOP_LIVE=1 可发起真实签名校验。",
    }
