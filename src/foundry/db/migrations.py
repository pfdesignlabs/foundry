"""Forward-only migration runner for Foundry's database schema (WI_0013).

Vec tables (vec_chunks_*) are NOT migration-managed — use ensure_vec_table().
"""

from __future__ import annotations

import sqlite3

# schema_version is the bootstrap table, created before migrations run.
_CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  DATETIME NOT NULL DEFAULT (datetime('now'))
)
"""

_V1_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY,
    path            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    ingested_at     DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    source_id       TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    context_prefix  TEXT NOT NULL DEFAULT '',
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='porter ascii');

CREATE TABLE IF NOT EXISTS source_summaries (
    source_id       TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    summary_text    TEXT NOT NULL,
    generated_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source_id)
);
"""

# Append-only. Each entry: (version: int, sql: str).
# executescript() issues an implicit COMMIT before running.
MIGRATIONS: list[tuple[int, str]] = [
    (1, _V1_SQL),
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations in ascending version order.

    Idempotent: safe to call on a database at any version.
    Vec tables are NOT managed here — use ensure_vec_table() instead.
    """
    conn.execute(_CREATE_SCHEMA_VERSION)
    conn.commit()

    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row[0] is not None else 0

    for version, sql in MIGRATIONS:
        if version > current:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            conn.commit()
