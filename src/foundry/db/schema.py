"""Database schema DDL and initialization."""

from __future__ import annotations

import sqlite3

_CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  DATETIME NOT NULL DEFAULT (datetime('now'))
)
"""

_CREATE_SOURCES = """
CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY,
    path            TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    ingested_at     DATETIME NOT NULL DEFAULT (datetime('now'))
)
"""

_CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    source_id       TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    context_prefix  TEXT NOT NULL DEFAULT '',
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
)
"""

CURRENT_VERSION = 1


def initialize(conn: sqlite3.Connection) -> None:
    """Create all base tables and record schema version (idempotent)."""
    conn.execute(_CREATE_SCHEMA_VERSION)
    conn.execute(_CREATE_SOURCES)
    conn.execute(_CREATE_CHUNKS)

    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    if row[0] is None:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (CURRENT_VERSION,)
        )

    conn.commit()
