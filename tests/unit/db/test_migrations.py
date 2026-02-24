"""Tests for the forward-only migration runner (WI_0013)."""

from __future__ import annotations

import sqlite3

import pytest

from foundry.db.connection import Database
from foundry.db.migrations import MIGRATIONS, run_migrations


def _fresh_conn(tmp_path):
    """Open a new connection without running migrations."""
    db = Database(tmp_path / "test.db")
    return db.connect()


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','shadow') AND name=?", (name,)
    ).fetchone() is not None


# --- Bootstrap ---

def test_run_migrations_creates_schema_version(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    assert _table_exists(conn, "schema_version")
    conn.close()


def test_run_migrations_records_version(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == MIGRATIONS[-1][0]
    conn.close()


# --- Idempotency ---

def test_run_migrations_idempotent(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    run_migrations(conn)
    count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    assert count == len(MIGRATIONS)
    conn.close()


# --- Tables created ---

def test_run_migrations_creates_sources(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    assert _table_exists(conn, "sources")
    conn.close()


def test_run_migrations_creates_chunks(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    assert _table_exists(conn, "chunks")
    conn.close()


def test_run_migrations_creates_chunks_fts(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    assert _table_exists(conn, "chunks_fts")
    conn.close()


def test_run_migrations_creates_source_summaries(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    assert _table_exists(conn, "source_summaries")
    conn.close()


# --- Vec tables are NOT created by migrations ---

def test_run_migrations_does_not_create_vec_tables(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    vec_tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE name LIKE 'vec_chunks_%'"
    ).fetchall()
    assert vec_tables == []
    conn.close()


# --- Incremental application ---

def test_run_migrations_applies_only_pending(tmp_path):
    """Simulate a DB already at version 1; a hypothetical v2 migration applies."""
    conn = _fresh_conn(tmp_path)

    # Manually set schema_version to 1 (no tables needed for this test)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL, applied_at DATETIME NOT NULL DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.commit()

    applied = []

    def mock_migrations():
        return [(1, "SELECT 1;"), (2, "SELECT 2;")]

    # Patch MIGRATIONS temporarily
    import foundry.db.migrations as mod
    original = mod.MIGRATIONS
    mod.MIGRATIONS = [(1, "SELECT 1;"), (2, "CREATE TABLE IF NOT EXISTS v2_marker (x INTEGER);")]
    try:
        run_migrations(conn)
        # v1 must NOT be re-applied (v2_marker came from v2 only)
        assert _table_exists(conn, "v2_marker")
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()]
        assert versions == [1, 2]
    finally:
        mod.MIGRATIONS = original
    conn.close()


# --- initialize() delegates to run_migrations() ---

def test_initialize_delegates_to_run_migrations(tmp_path):
    from foundry.db.schema import initialize
    conn = _fresh_conn(tmp_path)
    initialize(conn)
    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == MIGRATIONS[-1][0]
    conn.close()
