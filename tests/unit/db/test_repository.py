"""Tests for the Repository pattern (WI_0015)."""

from __future__ import annotations

import json

import pytest

from foundry.db.models import Chunk, Source
from foundry.db.repository import Repository
from foundry.db.vectors import ensure_vec_table, model_to_slug


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


def _source(id="src-1", path="doc.md", hash="abc123", model="openai/text-embedding-3-small"):
    return Source(id=id, path=path, content_hash=hash, embedding_model=model)


def _chunk(source_id="src-1", index=0, text="hello world", prefix="", meta="{}"):
    return Chunk(source_id=source_id, chunk_index=index, text=text, context_prefix=prefix, metadata=meta)


# ------------------------------------------------------------------
# Sources
# ------------------------------------------------------------------

def test_add_and_get_source(repo):
    s = _source()
    repo.add_source(s)
    result = repo.get_source("src-1")
    assert result is not None
    assert result.id == "src-1"
    assert result.path == "doc.md"


def test_get_source_not_found(repo):
    assert repo.get_source("nonexistent") is None


def test_get_source_by_path(repo):
    repo.add_source(_source(path="firmware.md"))
    result = repo.get_source_by_path("firmware.md")
    assert result is not None
    assert result.path == "firmware.md"


def test_list_sources_empty(repo):
    assert repo.list_sources() == []


def test_list_sources(repo):
    repo.add_source(_source(id="s1", path="a.md"))
    repo.add_source(_source(id="s2", path="b.md"))
    sources = repo.list_sources()
    assert len(sources) == 2
    paths = {s.path for s in sources}
    assert paths == {"a.md", "b.md"}


def test_delete_source(repo):
    repo.add_source(_source())
    repo.delete_source("src-1")
    assert repo.get_source("src-1") is None


# ------------------------------------------------------------------
# Chunks
# ------------------------------------------------------------------

def test_add_chunk_returns_rowid(repo):
    repo.add_source(_source())
    rowid = repo.add_chunk(_chunk())
    assert isinstance(rowid, int)
    assert rowid >= 1


def test_add_chunk_rowids_sequential(repo):
    repo.add_source(_source())
    r1 = repo.add_chunk(_chunk(index=0, text="first"))
    r2 = repo.add_chunk(_chunk(index=1, text="second"))
    assert r2 == r1 + 1


def test_get_chunk_by_rowid(repo):
    repo.add_source(_source())
    rowid = repo.add_chunk(_chunk(text="DMX512 protocol"))
    chunk = repo.get_chunk_by_rowid(rowid)
    assert chunk is not None
    assert chunk.text == "DMX512 protocol"
    assert chunk.rowid == rowid


def test_get_chunk_not_found(repo):
    assert repo.get_chunk_by_rowid(9999) is None


def test_count_chunks_by_source(repo):
    repo.add_source(_source())
    repo.add_chunk(_chunk(index=0))
    repo.add_chunk(_chunk(index=1))
    assert repo.count_chunks_by_source("src-1") == 2


def test_delete_chunks_by_source_removes_chunks(repo):
    repo.add_source(_source())
    repo.add_chunk(_chunk(index=0))
    repo.add_chunk(_chunk(index=1))
    repo.delete_chunks_by_source("src-1")
    assert repo.count_chunks_by_source("src-1") == 0


def test_delete_chunks_by_source_removes_fts(repo, tmp_db):
    repo.add_source(_source())
    repo.add_chunk(_chunk(text="DMX512 protocol"))
    repo.delete_chunks_by_source("src-1")
    fts_rows = tmp_db.execute(
        "SELECT rowid FROM chunks_fts WHERE text MATCH 'DMX512'"
    ).fetchall()
    assert fts_rows == []


def test_chunk_metadata_roundtrip(repo):
    repo.add_source(_source())
    meta = json.dumps({"source_type": "pdf", "page": 3})
    rowid = repo.add_chunk(_chunk(meta=meta))
    chunk = repo.get_chunk_by_rowid(rowid)
    assert chunk.metadata_dict == {"source_type": "pdf", "page": 3}


# ------------------------------------------------------------------
# FTS5 search
# ------------------------------------------------------------------

def test_search_fts_returns_match(repo):
    repo.add_source(_source())
    repo.add_chunk(_chunk(index=0, text="DMX512 protocol timing specification"))
    repo.add_chunk(_chunk(index=1, text="WiFi antenna placement guide"))

    results = repo.search_fts("DMX512", limit=5)
    assert len(results) >= 1
    texts = [c.text for c, _ in results]
    assert any("DMX512" in t for t in texts)


def test_search_fts_no_match(repo):
    repo.add_source(_source())
    repo.add_chunk(_chunk(text="unrelated content"))
    results = repo.search_fts("DMX512")
    assert results == []


def test_search_fts_returns_chunk_and_score(repo):
    repo.add_source(_source())
    repo.add_chunk(_chunk(text="LED driver circuit design"))
    results = repo.search_fts("LED driver")
    assert len(results) == 1
    chunk, score = results[0]
    assert isinstance(chunk, Chunk)
    assert isinstance(score, float)


def test_search_fts_query_with_commas_does_not_raise(repo):
    """FTS5 MATCH rejects commas as syntax errors — query must be sanitised."""
    repo.add_source(_source())
    repo.add_chunk(_chunk(text="clinical AI architecture retrieval evaluation"))
    # Should not raise OperationalError: fts5: syntax error near ","
    results = repo.search_fts("clinical AI architecture, retrieval, evaluation")
    assert isinstance(results, list)


def test_search_fts_query_with_special_chars_does_not_raise(repo):
    """Other punctuation (dots, colons) in queries must also be handled safely."""
    repo.add_source(_source())
    repo.add_chunk(_chunk(text="grounding best practices"))
    results = repo.search_fts("grounding: best practices.")
    assert isinstance(results, list)


# ------------------------------------------------------------------
# Vec embeddings
# ------------------------------------------------------------------

def test_add_and_search_vec(repo, tmp_db):
    repo.add_source(_source())
    rowid = repo.add_chunk(_chunk(text="DMX512 timing"))
    slug = model_to_slug("openai/text-embedding-3-small")
    table = ensure_vec_table(tmp_db, slug, dimensions=4)
    embedding = [0.1, 0.2, 0.3, 0.4]
    repo.add_embedding(table, rowid, embedding)

    results = repo.search_vec(table, embedding, limit=5)
    assert len(results) == 1
    chunk, distance = results[0]
    assert chunk.rowid == rowid
    assert chunk.text == "DMX512 timing"
    assert isinstance(distance, float)


def test_search_vec_empty_table(repo, tmp_db):
    slug = model_to_slug("openai/text-embedding-3-small")
    table = ensure_vec_table(tmp_db, slug, dimensions=4)
    results = repo.search_vec(table, [0.1, 0.2, 0.3, 0.4])
    assert results == []


# ------------------------------------------------------------------
# Source summaries
# ------------------------------------------------------------------

def test_add_and_get_summary(repo):
    repo.add_source(_source())
    repo.add_summary("src-1", "Summary of the DMX512 datasheet.")
    result = repo.get_summary("src-1")
    assert result == "Summary of the DMX512 datasheet."


def test_get_summary_not_found(repo):
    assert repo.get_summary("nonexistent") is None


def test_add_summary_upsert(repo):
    repo.add_source(_source())
    repo.add_summary("src-1", "First summary.")
    repo.add_summary("src-1", "Updated summary.")
    assert repo.get_summary("src-1") == "Updated summary."


def test_list_summaries(repo):
    repo.add_source(_source(id="s1", path="a.md"))
    repo.add_source(_source(id="s2", path="b.md"))
    repo.add_summary("s1", "Summary A")
    repo.add_summary("s2", "Summary B")
    summaries = repo.list_summaries()
    assert len(summaries) == 2


def test_list_summaries_with_limit(repo):
    repo.add_source(_source(id="s1", path="a.md"))
    repo.add_source(_source(id="s2", path="b.md"))
    repo.add_summary("s1", "Summary A")
    repo.add_summary("s2", "Summary B")
    summaries = repo.list_summaries(limit=1)
    assert len(summaries) == 1


def test_delete_summary(repo):
    repo.add_source(_source())
    repo.add_summary("src-1", "to be deleted")
    repo.delete_summary("src-1")
    assert repo.get_summary("src-1") is None
