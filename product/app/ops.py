"""Local operations: status, encrypted backup, and a support bundle."""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from . import db

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BACKUP_DIR = DATA / "backups"
LOG_DIR = DATA / "logs"
DB_PATH = DATA / "lira.duckdb"
VERSION = "0.2.0"


def _fernet() -> Fernet:
    configured = os.environ.get("LIRA_BACKUP_KEY")
    if configured:
        return Fernet(configured.encode("utf-8"))
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    key_path = BACKUP_DIR / "backup.key"
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
    return Fernet(key_path.read_bytes())


def status() -> dict[str, Any]:
    with db.session() as con:
        snapshot = db.snapshot_id(con)
        counts = db._counts(con)
        last_sync = con.execute("SELECT max(synced_at) FROM ops.sync_run").fetchone()[0]
        runs = con.execute("SELECT count(*) FROM ops.analysis_run").fetchone()[0]
    backups = sorted(BACKUP_DIR.glob("*.enc"))
    return {
        "version": VERSION,
        "snapshot_id": snapshot,
        "counts": counts,
        "analysis_runs": int(runs),
        "last_sync": last_sync.isoformat() if hasattr(last_sync, "isoformat") else last_sync,
        "db_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "backups": [
            {"file": path.name, "bytes": path.stat().st_size}
            for path in backups[-5:]
        ],
        "backup_key": "env" if os.environ.get("LIRA_BACKUP_KEY") else "local",
    }


def backup() -> dict[str, Any]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if DB_PATH.exists():
            archive.write(DB_PATH, "lira.duckdb")
        for folder in ("secrets", "logs"):
            base = DATA / folder
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    archive.write(path, str(path.relative_to(DATA)))
        archive.writestr(
            "status.json", json.dumps(status(), ensure_ascii=False, default=str)
        )
    encrypted = _fernet().encrypt(buffer.getvalue())
    name = f"backup-{time.strftime('%Y%m%d-%H%M%S')}.zip.enc"
    path = BACKUP_DIR / name
    path.write_bytes(encrypted)
    return {"file": name, "bytes": len(encrypted)}


def diagnostics() -> bytes:
    buffer = io.BytesIO()
    log_files = LOG_DIR.rglob("*") if LOG_DIR.exists() else []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in log_files:
            if path.is_file():
                archive.write(path, str(path.relative_to(DATA)))
        archive.writestr(
            "status.json", json.dumps(status(), ensure_ascii=False, default=str)
        )
    return buffer.getvalue()
