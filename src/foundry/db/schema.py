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

# WI_0012b: FTS5 virtual table for BM25 full-text search.
# Rows are inserted explicitly (rowid = chunks.rowid) by the repository.
_CREATE_CHUNKS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='porter ascii')
"""

# WI_0012c: Source summaries — one summary per ingested document.
_CREATE_SOURCE_SUMMARIES = """
CREATE TABLE IF NOT EXISTS source_summaries (
    source_id       TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    summary_text    TEXT NOT NULL,
    generated_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source_id)
)
"""

CURRENT_VERSION = 1


def initialize(conn: sqlite3.Connection) -> None:
    """Initialize the database schema via the migration runner (idempotent)."""
    from foundry.db.migrations import run_migrations

    run_migrations(conn)
