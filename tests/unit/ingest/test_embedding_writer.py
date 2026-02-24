"""Tests for EmbeddingWriter (WI_0022)."""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock, call, patch

import pytest

from foundry.db.models import Chunk, Source
from foundry.db.repository import Repository
from foundry.db.vectors import ensure_vec_table, model_to_slug
from foundry.ingest.embedding_writer import EmbeddingConfig, EmbeddingWriter


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def repo(tmp_db):
    r = Repository(tmp_db)
    r.add_source(
        Source(id="src-1", path="doc.md", content_hash="abc", embedding_model="openai/text-embedding-3-small")
    )
    return r


@pytest.fixture
def vec_table(tmp_db):
    slug = model_to_slug("openai/text-embedding-3-small")
    return ensure_vec_table(tmp_db, slug, dimensions=3)


def _mock_litellm(embed_vector: list[float] | None = None, prefix: str = "Context: DMX."):
    """Patch litellm.completion and litellm.embedding."""
    embed_vector = embed_vector or [0.1, 0.2, 0.3]

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = prefix

    mock_embedding = MagicMock()
    mock_embedding.data = [{"embedding": embed_vector}]

    return (
        patch("foundry.ingest.embedding_writer.litellm.completion", return_value=mock_completion),
        patch("foundry.ingest.embedding_writer.litellm.embedding", return_value=mock_embedding),
    )


# ------------------------------------------------------------------
# EmbeddingConfig defaults
# ------------------------------------------------------------------


def test_embedding_config_defaults():
    cfg = EmbeddingConfig()
    assert cfg.model == "openai/text-embedding-3-small"
    assert cfg.context_model == "openai/gpt-4o-mini"
    assert cfg.dimensions == 1536


# ------------------------------------------------------------------
# Expensive model warning
# ------------------------------------------------------------------


def test_expensive_model_warning():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        EmbeddingWriter(MagicMock(), EmbeddingConfig(context_model="openai/gpt-4o"))
    assert any("expensive" in str(warning.message) for warning in w)


def test_cheap_model_no_warning():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        EmbeddingWriter(MagicMock(), EmbeddingConfig(context_model="openai/gpt-4o-mini"))
    assert not any("expensive" in str(warning.message) for warning in w)


# ------------------------------------------------------------------
# API key check
# ------------------------------------------------------------------


def test_no_api_key_raises(repo, vec_table, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    writer = EmbeddingWriter(repo, EmbeddingConfig())
    chunk = Chunk(source_id="src-1", chunk_index=0, text="Test chunk.")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        writer.write([chunk], vec_table)


# ------------------------------------------------------------------
# write() — full pipeline
# ------------------------------------------------------------------


def test_write_returns_rowids(repo, vec_table, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    ctx, emb = _mock_litellm()
    with ctx, emb:
        writer = EmbeddingWriter(repo, EmbeddingConfig())
        chunks = [
            Chunk(source_id="src-1", chunk_index=0, text="Chunk A"),
            Chunk(source_id="src-1", chunk_index=1, text="Chunk B"),
        ]
        rowids = writer.write(chunks, vec_table)
    assert len(rowids) == 2
    assert all(isinstance(r, int) for r in rowids)
    assert rowids[1] == rowids[0] + 1


def test_write_stores_context_prefix(repo, vec_table, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    ctx, emb = _mock_litellm(prefix="Context about DMX512.")
    with ctx, emb:
        writer = EmbeddingWriter(repo, EmbeddingConfig())
        chunk = Chunk(source_id="src-1", chunk_index=0, text="Some text.")
        rowids = writer.write([chunk], vec_table)

    stored = repo.get_chunk_by_rowid(rowids[0])
    assert stored.context_prefix == "Context about DMX512."


def test_write_chunk_text_unchanged(repo, vec_table, monkeypatch):
    """Chunk text must be stored as-is, prefix only affects embedding input."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    ctx, emb = _mock_litellm(prefix="Context.")
    with ctx, emb:
        writer = EmbeddingWriter(repo, EmbeddingConfig())
        chunk = Chunk(source_id="src-1", chunk_index=0, text="Original text.")
        rowids = writer.write([chunk], vec_table)

    stored = repo.get_chunk_by_rowid(rowids[0])
    assert stored.text == "Original text."


def test_write_embedding_stored_in_vec(repo, vec_table, monkeypatch, tmp_db):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    embed_vec = [0.5, 0.6, 0.7]
    ctx, emb = _mock_litellm(embed_vector=embed_vec)
    with ctx, emb:
        writer = EmbeddingWriter(repo, EmbeddingConfig())
        chunk = Chunk(source_id="src-1", chunk_index=0, text="Embedded text.")
        rowids = writer.write([chunk], vec_table)

    # Vec search should return our chunk
    results = repo.search_vec(vec_table, embed_vec, limit=1)
    assert len(results) == 1
    assert results[0][0].rowid == rowids[0]


def test_write_empty_prefix_still_embeds_chunk_text(repo, vec_table, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    ctx, emb = _mock_litellm(prefix="   ")  # whitespace-only prefix

    embed_calls = []

    real_emb = MagicMock()
    real_emb.data = [{"embedding": [0.1, 0.2, 0.3]}]

    with ctx:
        with patch("foundry.ingest.embedding_writer.litellm.embedding", return_value=real_emb) as mock_emb:
            writer = EmbeddingWriter(repo, EmbeddingConfig())
            chunk = Chunk(source_id="src-1", chunk_index=0, text="Just the text.")
            writer.write([chunk], vec_table)

    # When prefix is whitespace, embed text should be just the chunk text
    called_with = mock_emb.call_args[1]["input"][0] if mock_emb.call_args[1] else mock_emb.call_args[0][1][0]
    assert called_with == "Just the text."


def test_prefix_generation_failure_falls_back_to_empty(repo, vec_table, monkeypatch):
    """If LLM call for prefix fails, fall back to empty prefix (non-fatal)."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")

    mock_completion = MagicMock(side_effect=Exception("LLM error"))
    mock_embedding = MagicMock()
    mock_embedding.return_value.data = [{"embedding": [0.1, 0.2, 0.3]}]

    with patch("foundry.ingest.embedding_writer.litellm.completion", mock_completion):
        with patch("foundry.ingest.embedding_writer.litellm.embedding", mock_embedding):
            writer = EmbeddingWriter(repo, EmbeddingConfig())
            chunk = Chunk(source_id="src-1", chunk_index=0, text="Some text.")
            rowids = writer.write([chunk], vec_table)

    stored = repo.get_chunk_by_rowid(rowids[0])
    assert stored.context_prefix == ""


# ------------------------------------------------------------------
# on_progress callback (WI_0035)
# ------------------------------------------------------------------


def test_write_calls_on_progress_per_chunk(repo, vec_table, monkeypatch):
    """on_progress is called once per chunk with zero-based index."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    ctx, emb = _mock_litellm()

    progress_calls: list[int] = []

    with ctx, emb:
        writer = EmbeddingWriter(repo, EmbeddingConfig())
        chunks = [
            Chunk(source_id="src-1", chunk_index=0, text="Chunk A"),
            Chunk(source_id="src-1", chunk_index=1, text="Chunk B"),
            Chunk(source_id="src-1", chunk_index=2, text="Chunk C"),
        ]
        writer.write(chunks, vec_table, on_progress=progress_calls.append)

    assert progress_calls == [0, 1, 2]


def test_write_no_progress_callback_is_ok(repo, vec_table, monkeypatch):
    """on_progress=None (default) does not raise."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    ctx, emb = _mock_litellm()

    with ctx, emb:
        writer = EmbeddingWriter(repo, EmbeddingConfig())
        chunk = Chunk(source_id="src-1", chunk_index=0, text="Chunk A")
        rowids = writer.write([chunk], vec_table)  # no on_progress arg

    assert len(rowids) == 1


def test_write_on_progress_called_after_db_write(repo, vec_table, monkeypatch):
    """on_progress fires after the chunk is persisted (not before)."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    ctx, emb = _mock_litellm()

    stored_at_progress: list[int] = []

    def _callback(idx: int) -> None:
        # At callback time, idx+1 chunks should be in the DB
        count = repo.count_chunks_by_source("src-1")
        stored_at_progress.append(count)

    with ctx, emb:
        writer = EmbeddingWriter(repo, EmbeddingConfig())
        chunks = [
            Chunk(source_id="src-1", chunk_index=0, text="A"),
            Chunk(source_id="src-1", chunk_index=1, text="B"),
        ]
        writer.write(chunks, vec_table, on_progress=_callback)

    # After chunk 0: 1 in DB; after chunk 1: 2 in DB
    assert stored_at_progress == [1, 2]
