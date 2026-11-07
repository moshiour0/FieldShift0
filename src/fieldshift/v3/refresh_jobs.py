"""Persistent, deduplicated NASA POWER refresh jobs.

SQLite is for a single-host development worker. Production requires PostgreSQL
and shared object storage; Vercel requests never perform long-running ingestion.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .history import region_by_id

SCHEMA = """CREATE TABLE IF NOT EXISTS refresh_jobs (
 id TEXT PRIMARY KEY, job_key TEXT NOT NULL UNIQUE, region_id TEXT NOT NULL,
 product TEXT NOT NULL, data_through TEXT NOT NULL, owner_hash TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, next_attempt_at TEXT NOT NULL,
 error TEXT, published_through TEXT
)"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _mode() -> str:
    if os.getenv("FIELD_SHIFT_JOBS_DSN", "").strip():
        return "postgres"
    if os.getenv("VERCEL"):
        raise RuntimeError("Refresh unavailable: configure FIELD_SHIFT_JOBS_DSN and durable archive object storage")
    return "sqlite"


@contextmanager
def _conn() -> Iterator[Any]:
    if _mode() == "postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Production refresh jobs require psycopg[binary]") from exc
        with psycopg.connect(os.environ["FIELD_SHIFT_JOBS_DSN"], row_factory=dict_row) as db:
            db.execute(SCHEMA)
            yield db
    else:
        path = Path(os.getenv("FIELD_SHIFT_JOBS_SQLITE_PATH", "/tmp/krishinexus-refresh-jobs.sqlite3"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(path), timeout=12) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=12000")
            db.execute(SCHEMA)
            yield db


def _sql(db: Any, query: str, args: tuple = ()):
    if _mode() == "postgres":
        query = query.replace("?", "%s")
    return db.execute(query, args)


def _record(row: Any) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    return {key: value for key, value in data.items() if key not in {"job_key", "owner_hash"}}


def create_refresh(region_id: str, product: str, through: str, client_id: str) -> tuple[dict, bool]:
    region_by_id(region_id)
    if product != "power":
        raise ValueError("Only NASA POWER refresh is available; other products require QA-validated import.")
    try:
        end = date.fromisoformat(through)
    except (TypeError, ValueError) as exc:
        raise ValueError("data_through must use YYYY-MM-DD") from exc
    if end.year != date.today().year or not date(end.year, 1, 1) <= end < date.today():
        raise ValueError("data_through must be a past date in the current year")
    if not client_id:
        raise ValueError("Client identity is required for refresh rate limiting")
    salt = os.getenv("FIELD_SHIFT_RATE_LIMIT_SALT", "krishinexus-demo")
    owner = hashlib.sha256((salt + client_id).encode()).hexdigest()
    key = hashlib.sha256(f"power|{region_id}|{through}|v2".encode()).hexdigest()
    now = _now()
    cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with _conn() as db:
        existing = _sql(db, "SELECT * FROM refresh_jobs WHERE job_key=?", (key,)).fetchone()
        if existing:
            return _record(existing), False
        count_row = _sql(db, "SELECT COUNT(*) AS n FROM refresh_jobs WHERE owner_hash=? AND created_at>?",
                         (owner, cutoff)).fetchone()
        count = count_row["n"] if _mode() == "postgres" else count_row[0]
        if count >= int(os.getenv("FIELD_SHIFT_REFRESH_HOURLY_LIMIT", "3")):
            raise PermissionError("Hourly refresh limit reached; use cached data or try later.")
        pending_row = _sql(db, "SELECT COUNT(*) AS n FROM refresh_jobs WHERE status IN ('queued','fetching','qa','publishing')").fetchone()
        pending = pending_row["n"] if _mode() == "postgres" else pending_row[0]
        if pending >= int(os.getenv("FIELD_SHIFT_REFRESH_QUEUE_LIMIT", "40")):
            raise RuntimeError("Refresh queue is at capacity; cached history remains available.")
        job_id = str(uuid.uuid4())
        _sql(db, """INSERT INTO refresh_jobs
          (id,job_key,region_id,product,data_through,owner_hash,status,created_at,updated_at,next_attempt_at)
          VALUES (?,?,?,?,?,?,'queued',?,?,?) ON CONFLICT(job_key) DO NOTHING""",
             (job_id, key, region_id, product, through, owner, now, now, now))
        row = _sql(db, "SELECT * FROM refresh_jobs WHERE job_key=?", (key,)).fetchone()
        return _record(row), row["id"] == job_id


def get_refresh(job_id: str) -> dict | None:
    try:
        uuid.UUID(job_id)
    except ValueError:
        return None
    with _conn() as db:
        return _record(_sql(db, "SELECT * FROM refresh_jobs WHERE id=?", (job_id,)).fetchone())


def claim_refresh() -> dict | None:
    now = _now()
    with _conn() as db:
        if _mode() == "postgres":
            row = _sql(db, """UPDATE refresh_jobs SET status='fetching',attempts=attempts+1,updated_at=?
              WHERE id=(SELECT id FROM refresh_jobs WHERE status='queued' AND next_attempt_at<=?
                        ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
              RETURNING *""", (now, now)).fetchone()
            return _record(row)
        db.execute("BEGIN IMMEDIATE")
        row = _sql(db, "SELECT * FROM refresh_jobs WHERE status='queued' AND next_attempt_at<=? ORDER BY created_at LIMIT 1",
                   (now,)).fetchone()
        if row:
            _sql(db, "UPDATE refresh_jobs SET status='fetching',attempts=attempts+1,updated_at=? WHERE id=?",
                 (now, row["id"]))
            row = _sql(db, "SELECT * FROM refresh_jobs WHERE id=?", (row["id"],)).fetchone()
        return _record(row)


def update_refresh(job_id: str, status: str, *, error: str | None = None,
                   published_through: str | None = None) -> None:
    if status not in {"queued", "fetching", "qa", "publishing", "ready", "failed"}:
        raise ValueError("Invalid refresh job state")
    with _conn() as db:
        _sql(db, "UPDATE refresh_jobs SET status=?,updated_at=?,error=?,published_through=? WHERE id=?",
             (status, _now(), error[:350] if error else None, published_through, job_id))


def retry_refresh(job_id: str, attempts: int, reason: str) -> None:
    if attempts >= 3:
        update_refresh(job_id, "failed", error=reason)
        return
    next_at = (datetime.now(UTC) + timedelta(seconds=min(900, 30 * 2 ** attempts))).isoformat()
    with _conn() as db:
        _sql(db, "UPDATE refresh_jobs SET status='queued',updated_at=?,next_attempt_at=?,error=? WHERE id=?",
             (_now(), next_at, reason[:350], job_id))
