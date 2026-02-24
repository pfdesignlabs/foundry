"""Tests for database schema initialization (WI_0012, WI_0012b, WI_0012c)."""

from __future__ import annotations

import foundry.db.schema as schema_module
from foundry.db.schema import CURRENT_VERSION, initialize


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def test_sources_table_exists(tmp_db):
    assert _table_exists(tmp_db, "sources")


def test_sources_columns(tmp_db):
    cols = _table_columns(tmp_db, "sources")
    assert cols == {"id", "path", "content_hash", "embedding_model", "ingested_at"}


def test_chunks_table_exists(tmp_db):
    assert _table_exists(tmp_db, "chunks")


def test_chunks_columns(tmp_db):
    cols = _table_columns(tmp_db, "chunks")
    assert cols == {"source_id", "chunk_index", "text", "context_prefix", "metadata", "created_at"}


def test_schema_version_table_exists(tmp_db):
    assert _table_exists(tmp_db, "schema_version")


def test_schema_version_recorded(tmp_db):
    version = tmp_db.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == CURRENT_VERSION


def test_initialize_idempotent(tmp_db):
    # Calling initialize twice must not raise and version must stay the same
    initialize(tmp_db)
    rows = tmp_db.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    assert rows == 1


def test_chunks_rowid_is_implicit(tmp_db):
    # chunks table must have an implicit rowid (no WITHOUT ROWID)
    tmp_db.execute("INSERT INTO sources (id, path, content_hash, embedding_model) VALUES (?, ?, ?, ?)",
                   ("src-1", "doc.md", "abc123", "openai/text-embedding-3-small"))
    tmp_db.execute(
        "INSERT INTO chunks (source_id, chunk_index, text) VALUES (?, ?, ?)",
        ("src-1", 0, "hello world"),
    )
    row = tmp_db.execute("SELECT rowid, text FROM chunks").fetchone()
    assert row["rowid"] == 1
    assert row["text"] == "hello world"


def test_sources_foreign_key_cascade(tmp_db):
    # Deleting a source must cascade-delete its chunks
    tmp_db.execute("INSERT INTO sources (id, path, content_hash, embedding_model) VALUES (?, ?, ?, ?)",
                   ("src-del", "x.md", "hash", "model"))
    tmp_db.execute(
        "INSERT INTO chunks (source_id, chunk_index, text) VALUES (?, ?, ?)",
        ("src-del", 0, "text"),
    )
    tmp_db.execute("DELETE FROM sources WHERE id = ?", ("src-del",))
    tmp_db.commit()
    count = tmp_db.execute("SELECT COUNT(*) FROM chunks WHERE source_id = ?", ("src-del",)).fetchone()[0]
    assert count == 0


# --- WI_0012b: FTS5 virtual table ---

def test_chunks_fts_table_exists(tmp_db):
    row = tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE name='chunks_fts'"
    ).fetchone()
    assert row is not None


def test_chunks_fts_bm25_search(tmp_db):
    # Insert with explicit rowid matching chunks.rowid
    tmp_db.execute("INSERT INTO chunks_fts(rowid, text) VALUES (1, 'DMX512 protocol timing')")
    tmp_db.execute("INSERT INTO chunks_fts(rowid, text) VALUES (2, 'WiFi antenna placement')")
    tmp_db.execute("INSERT INTO chunks_fts(rowid, text) VALUES (3, 'DMX receiver circuit design')")

    rows = tmp_db.execute(
        "SELECT rowid FROM chunks_fts WHERE text MATCH 'DMX512' ORDER BY bm25(chunks_fts)"
    ).fetchall()
    rowids = [r[0] for r in rows]
    assert 1 in rowids
    assert 2 not in rowids


def test_chunks_fts_rowid_matches_chunks(tmp_db):
    # rowid in FTS must be settable to an arbitrary integer (chunks.rowid mapping)
    tmp_db.execute("INSERT INTO chunks_fts(rowid, text) VALUES (42, 'LED driver circuit')")
    row = tmp_db.execute(
        "SELECT rowid FROM chunks_fts WHERE text MATCH 'LED'"
    ).fetchone()
    assert row[0] == 42


# --- WI_0012c: source_summaries table ---

def test_source_summaries_table_exists(tmp_db):
    assert _table_exists(tmp_db, "source_summaries")


def test_source_summaries_columns(tmp_db):
    cols = _table_columns(tmp_db, "source_summaries")
    assert cols == {"source_id", "summary_text", "generated_at"}


def test_source_summaries_insert_and_retrieve(tmp_db):
    tmp_db.execute(
        "INSERT INTO sources (id, path, content_hash, embedding_model) VALUES (?, ?, ?, ?)",
        ("src-sum", "doc.pdf", "hash123", "openai/text-embedding-3-small"),
    )
    tmp_db.execute(
        "INSERT INTO source_summaries (source_id, summary_text) VALUES (?, ?)",
        ("src-sum", "A document about DMX512 protocol specifications."),
    )
    row = tmp_db.execute(
        "SELECT summary_text FROM source_summaries WHERE source_id = ?", ("src-sum",)
    ).fetchone()
    assert "DMX512" in row["summary_text"]


def test_source_summaries_cascade_delete(tmp_db):
    tmp_db.execute(
        "INSERT INTO sources (id, path, content_hash, embedding_model) VALUES (?, ?, ?, ?)",
        ("src-del2", "x.pdf", "h", "model"),
    )
    tmp_db.execute(
        "INSERT INTO source_summaries (source_id, summary_text) VALUES (?, ?)",
        ("src-del2", "summary text"),
    )
    tmp_db.execute("DELETE FROM sources WHERE id = ?", ("src-del2",))
    tmp_db.commit()
    count = tmp_db.execute(
        "SELECT COUNT(*) FROM source_summaries WHERE source_id = ?", ("src-del2",)
    ).fetchone()[0]
    assert count == 0
