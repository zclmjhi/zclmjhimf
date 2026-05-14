"""
SQLite persistence layer. All tables are created on first import.
Every function is synchronous and safe to call from any thread.
"""

import json
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import config


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

@contextmanager
def _conn():
    con = sqlite3.connect(config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    name        TEXT PRIMARY KEY,
    keywords    TEXT NOT NULL,          -- JSON list
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_alert_feeds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL REFERENCES clients(name) ON DELETE CASCADE,
    feed_url    TEXT NOT NULL,
    label       TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE(client_name, feed_url)
);

CREATE TABLE IF NOT EXISTS briefs (
    id                  TEXT PRIMARY KEY,   -- uuid4
    user_id             TEXT NOT NULL,
    user_email          TEXT,
    title               TEXT NOT NULL,
    clients             TEXT NOT NULL,      -- JSON list of client names
    extra_keywords      TEXT NOT NULL,      -- JSON list
    delivery_channel    TEXT NOT NULL,      -- 'teams' | 'email'
    delivery_schedule   TEXT NOT NULL,      -- 'immediate' | 'scheduled' | 'on_demand'
    schedule_cron       TEXT,               -- cron expression for scheduled briefs
    next_delivery_at    TEXT,               -- ISO timestamp for next digest
    priority            INTEGER NOT NULL DEFAULT 0,
    expires_at          TEXT,               -- ISO timestamp or NULL for open-ended
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    active              INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS seen_items (
    url             TEXT PRIMARY KEY,
    content_hash    TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    last_modified   TEXT
);

CREATE TABLE IF NOT EXISTS coverage_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id        TEXT REFERENCES briefs(id),
    client_name     TEXT,
    keyword_matched TEXT,
    headline        TEXT NOT NULL,
    url             TEXT NOT NULL,
    source_name     TEXT,
    published_at    TEXT,
    delivered_at    TEXT NOT NULL,
    delivery_channel TEXT NOT NULL,
    is_update       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS noise_terms (
    term        TEXT PRIMARY KEY,
    added_at    TEXT NOT NULL
);

INSERT OR IGNORE INTO noise_terms (term, added_at) VALUES
    ('job listing', datetime('now')),
    ('we are hiring', datetime('now')),
    ('stock price', datetime('now')),
    ('share price', datetime('now')),
    ('earnings per share', datetime('now')),
    ('vacancy', datetime('now')),
    ('recruitment', datetime('now')),
    ('careers', datetime('now'));
"""


def init_db() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# Client registry
# ---------------------------------------------------------------------------

def list_clients() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM clients ORDER BY name").fetchall()
    return [_to_dict(r) for r in rows]


def get_client(name: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM clients WHERE lower(name) = lower(?)", (name,)
        ).fetchone()
    return _to_dict(row) if row else None


def upsert_client(name: str, keywords: list[str]) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO clients (name, keywords, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                keywords   = excluded.keywords,
                updated_at = excluded.updated_at
            """,
            (name, json.dumps(keywords), now, now),
        )


def delete_client(name: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM clients WHERE lower(name) = lower(?)", (name,))
    return cur.rowcount > 0


def get_client_keywords(name: str) -> list[str]:
    client = get_client(name)
    if not client:
        return []
    return json.loads(client["keywords"])


# ---------------------------------------------------------------------------
# Google Alert feeds
# ---------------------------------------------------------------------------

def add_google_alert_feed(client_name: str, feed_url: str, label: str = "") -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO google_alert_feeds (client_name, feed_url, label, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (client_name, feed_url, label, _now()),
        )


def list_google_alert_feeds() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM google_alert_feeds").fetchall()
    return [_to_dict(r) for r in rows]


def delete_google_alert_feeds_for_client(client_name: str) -> None:
    with _conn() as con:
        con.execute(
            "DELETE FROM google_alert_feeds WHERE lower(client_name) = lower(?)",
            (client_name,),
        )


# ---------------------------------------------------------------------------
# Briefs
# ---------------------------------------------------------------------------

import uuid


def create_brief(
    user_id: str,
    user_email: str | None,
    title: str,
    clients: list[str],
    extra_keywords: list[str],
    delivery_channel: str,
    delivery_schedule: str,
    schedule_cron: str | None,
    next_delivery_at: str | None,
    priority: bool,
    expires_at: str | None,
) -> str:
    brief_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO briefs (
                id, user_id, user_email, title, clients, extra_keywords,
                delivery_channel, delivery_schedule, schedule_cron,
                next_delivery_at, priority, expires_at, created_at, updated_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                brief_id,
                user_id,
                user_email,
                title,
                json.dumps(clients),
                json.dumps(extra_keywords),
                delivery_channel,
                delivery_schedule,
                schedule_cron,
                next_delivery_at,
                1 if priority else 0,
                expires_at,
                now,
                now,
            ),
        )
    return brief_id


def get_brief(brief_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    return _to_dict(row) if row else None


def list_active_briefs(user_id: str | None = None) -> list[dict]:
    with _conn() as con:
        if user_id:
            rows = con.execute(
                "SELECT * FROM briefs WHERE active = 1 AND user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM briefs WHERE active = 1 ORDER BY created_at"
            ).fetchall()
    return [_to_dict(r) for r in rows]


def update_brief(brief_id: str, **fields: Any) -> bool:
    allowed = {
        "title", "clients", "extra_keywords", "delivery_channel",
        "delivery_schedule", "schedule_cron", "next_delivery_at",
        "priority", "expires_at", "active",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    # Serialise lists
    for key in ("clients", "extra_keywords"):
        if key in updates and isinstance(updates[key], list):
            updates[key] = json.dumps(updates[key])
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [brief_id]
    with _conn() as con:
        cur = con.execute(
            f"UPDATE briefs SET {set_clause} WHERE id = ?", values
        )
    return cur.rowcount > 0


def deactivate_brief(brief_id: str) -> bool:
    return update_brief(brief_id, active=0)


def deactivate_all_briefs_for_user(user_id: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "UPDATE briefs SET active = 0, updated_at = ? WHERE user_id = ? AND active = 1",
            (_now(), user_id),
        )
    return cur.rowcount


def expire_stale_briefs() -> list[str]:
    """Deactivate briefs whose expires_at has passed. Returns list of expired IDs."""
    now = _now()
    with _conn() as con:
        rows = con.execute(
            "SELECT id FROM briefs WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            con.execute(
                f"UPDATE briefs SET active = 0, updated_at = ? WHERE id IN ({','.join('?'*len(ids))})",
                [now] + ids,
            )
    return ids


# ---------------------------------------------------------------------------
# Seen-item cache and update detection
# ---------------------------------------------------------------------------

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def is_seen(url: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM seen_items WHERE url = ?", (url,)
        ).fetchone()
    return row is not None


def get_seen_item(url: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM seen_items WHERE url = ?", (url,)
        ).fetchone()
    return _to_dict(row) if row else None


def mark_seen(
    url: str,
    current_hash: str,
    last_modified: str | None = None,
) -> bool:
    """
    Insert or update the seen-item record.
    Returns True if this is a NEW item, False if it already existed.
    """
    now = _now()
    with _conn() as con:
        existing = con.execute(
            "SELECT content_hash FROM seen_items WHERE url = ?", (url,)
        ).fetchone()
        if existing is None:
            con.execute(
                """
                INSERT INTO seen_items (url, content_hash, first_seen_at, last_seen_at, last_modified)
                VALUES (?, ?, ?, ?, ?)
                """,
                (url, current_hash, now, now, last_modified),
            )
            return True
        else:
            con.execute(
                """
                UPDATE seen_items
                SET content_hash = ?, last_seen_at = ?, last_modified = ?
                WHERE url = ?
                """,
                (current_hash, now, last_modified, url),
            )
            return False


def has_content_changed(url: str, new_hash: str) -> bool:
    item = get_seen_item(url)
    if item is None:
        return True
    return item["content_hash"] != new_hash


# ---------------------------------------------------------------------------
# Coverage log
# ---------------------------------------------------------------------------

def log_coverage(
    brief_id: str | None,
    client_name: str | None,
    keyword_matched: str | None,
    headline: str,
    url: str,
    source_name: str | None,
    published_at: str | None,
    delivery_channel: str,
    is_update: bool = False,
) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO coverage_log (
                brief_id, client_name, keyword_matched, headline, url,
                source_name, published_at, delivered_at, delivery_channel, is_update
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                brief_id,
                client_name,
                keyword_matched,
                headline,
                url,
                source_name,
                published_at,
                _now(),
                delivery_channel,
                1 if is_update else 0,
            ),
        )


def query_coverage_log(
    brief_id: str | None = None,
    since: str | None = None,
    client_name: str | None = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if brief_id:
        clauses.append("brief_id = ?")
        params.append(brief_id)
    if since:
        clauses.append("delivered_at >= ?")
        params.append(since)
    if client_name:
        clauses.append("lower(client_name) = lower(?)")
        params.append(client_name)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM coverage_log {where} ORDER BY delivered_at DESC",
            params,
        ).fetchall()
    return [_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Noise filter
# ---------------------------------------------------------------------------

def list_noise_terms() -> list[str]:
    with _conn() as con:
        rows = con.execute("SELECT term FROM noise_terms ORDER BY term").fetchall()
    return [r["term"] for r in rows]


def add_noise_term(term: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO noise_terms (term, added_at) VALUES (lower(?), ?)",
            (term, _now()),
        )


def remove_noise_term(term: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM noise_terms WHERE lower(term) = lower(?)", (term,)
        )
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Initialise on import
# ---------------------------------------------------------------------------

init_db()
