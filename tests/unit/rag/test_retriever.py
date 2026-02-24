"""Tests for hybrid retriever + HyDE query expansion (WI_0024, WI_0024a)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from foundry.db.models import Chunk, Source
from foundry.db.repository import Repository
from foundry.db.vectors import ensure_vec_table, model_to_slug
from foundry.rag.retriever import (
    RetrieverConfig,
    ScoredChunk,
    _build_embed_query,
    _embed,
    _rrf_fuse,
    _validate_vec_table,
    retrieve,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_MODEL = "openai/text-embedding-3-small"
_DIMS = 1536
_SLUG = model_to_slug(_MODEL)

_FAKE_EMBEDDING = [0.1] * _DIMS


def _populate_db(conn, n: int = 3) -> list[int]:
    """Insert n chunks + embeddings; return rowids."""
    repo = Repository(conn)
    slug = model_to_slug(_MODEL)
    vec_table = ensure_vec_table(conn, slug, _DIMS)
    source = Source(
        id="src-1",
        path="doc.txt",
        content_hash="abc",
        embedding_model=_MODEL,
    )
    repo.add_source(source)
    rowids = []
    for i in range(n):
        rowid = repo.add_chunk(
            Chunk(source_id="src-1", chunk_index=i, text=f"chunk text number {i}")
        )
        repo.add_embedding(vec_table, rowid, _FAKE_EMBEDDING)
        rowids.append(rowid)
    return rowids


# ------------------------------------------------------------------
# RRF fusion unit tests
# ------------------------------------------------------------------


def _make_chunk(rowid: int) -> Chunk:
    return Chunk(
        source_id="src",
        chunk_index=rowid,
        text=f"text {rowid}",
        rowid=rowid,
    )


def test_rrf_fuse_combines_both_channels():
    dense = [(_make_chunk(1), 0.1), (_make_chunk(2), 0.2)]
    bm25 = [(_make_chunk(2), -1.0), (_make_chunk(3), -2.0)]
    result = _rrf_fuse(dense, bm25, top_k=10)
    rowids = [s.chunk.rowid for s in result]
    # chunk 2 appears in both → higher score → should be first
    assert rowids[0] == 2
    assert set(rowids) == {1, 2, 3}


def test_rrf_fuse_top_k_respected():
    dense = [(_make_chunk(i), float(i)) for i in range(20)]
    bm25 = [(_make_chunk(i), float(-i)) for i in range(20)]
    result = _rrf_fuse(dense, bm25, top_k=5)
    assert len(result) == 5


def test_rrf_fuse_dense_only_channel():
    dense = [(_make_chunk(1), 0.1), (_make_chunk(2), 0.2)]
    bm25: list = []
    result = _rrf_fuse(dense, bm25, top_k=10)
    assert len(result) == 2
    assert result[0].dense_rank == 1


def test_rrf_fuse_bm25_only_channel():
    dense: list = []
    bm25 = [(_make_chunk(5), -1.0), (_make_chunk(6), -2.0)]
    result = _rrf_fuse(dense, bm25, top_k=10)
    assert len(result) == 2
    assert result[0].bm25_rank == 1


def test_rrf_scores_sorted_descending():
    dense = [(_make_chunk(i), float(i)) for i in range(5)]
    bm25 = [(_make_chunk(i), float(-i)) for i in range(5)]
    result = _rrf_fuse(dense, bm25, top_k=10)
    scores = [s.rrf_score for s in result]
    assert scores == sorted(scores, reverse=True)


def test_rrf_chunk_in_both_lists_has_both_ranks():
    dense = [(_make_chunk(42), 0.9)]
    bm25 = [(_make_chunk(42), -0.5)]
    result = _rrf_fuse(dense, bm25, top_k=10)
    assert len(result) == 1
    sc = result[0]
    assert sc.dense_rank == 1
    assert sc.bm25_rank == 1


# ------------------------------------------------------------------
# Vec table validation
# ------------------------------------------------------------------


def test_validate_vec_table_raises_if_missing(tmp_db):
    with pytest.raises(RuntimeError, match="No embeddings found"):
        _validate_vec_table(tmp_db, "vec_chunks_nonexistent_model", "nonexistent/model")


def test_validate_vec_table_passes_if_exists(tmp_db):
    slug = model_to_slug(_MODEL)
    ensure_vec_table(tmp_db, slug, _DIMS)
    # Should not raise
    _validate_vec_table(tmp_db, f"vec_chunks_{slug}", _MODEL)


# ------------------------------------------------------------------
# HyDE expansion (WI_0024a)
# ------------------------------------------------------------------


def test_hyde_disabled_returns_raw_query():
    config = RetrieverConfig(hyde=False)
    result = _build_embed_query("What is the voltage?", config)
    assert result == "What is the voltage?"


def test_hyde_enabled_returns_llm_answer():
    config = RetrieverConfig(hyde=True, hyde_model="openai/gpt-4o-mini")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "The voltage is 3.3V."

    with patch("foundry.rag.retriever.litellm.completion", return_value=mock_response):
        result = _build_embed_query("What is the voltage?", config)

    assert result == "The voltage is 3.3V."


def test_hyde_failure_falls_back_to_raw_query():
    config = RetrieverConfig(hyde=True, hyde_model="openai/gpt-4o-mini")

    with patch(
        "foundry.rag.retriever.litellm.completion", side_effect=Exception("API error")
    ):
        result = _build_embed_query("What is the voltage?", config)

    assert result == "What is the voltage?"


def test_hyde_empty_response_falls_back_to_raw_query():
    config = RetrieverConfig(hyde=True, hyde_model="openai/gpt-4o-mini")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = None

    with patch("foundry.rag.retriever.litellm.completion", return_value=mock_response):
        result = _build_embed_query("my query", config)

    assert result == "my query"


# ------------------------------------------------------------------
# Embedding helper
# ------------------------------------------------------------------


def test_embed_calls_litellm_embedding():
    mock_response = MagicMock()
    mock_response.data = [{"embedding": [0.5] * 10}]

    with patch("foundry.rag.retriever.litellm.embedding", return_value=mock_response) as mock_emb:
        result = _embed("some text", "openai/text-embedding-3-small")

    mock_emb.assert_called_once_with(
        model="openai/text-embedding-3-small", input=["some text"]
    )
    assert result == [0.5] * 10


# ------------------------------------------------------------------
# Full retrieve() integration (with mocked LiteLLM)
# ------------------------------------------------------------------


def test_retrieve_raises_if_no_vec_table(tmp_db):
    config = RetrieverConfig(embedding_model=_MODEL)
    repo = Repository(tmp_db)

    with pytest.raises(RuntimeError, match="No embeddings found"):
        retrieve("test query", repo, config)


def test_retrieve_hybrid_returns_chunks(tmp_db):
    rowids = _populate_db(tmp_db)
    config = RetrieverConfig(embedding_model=_MODEL, mode="hybrid", top_k=5, hyde=False)
    repo = Repository(tmp_db)

    mock_emb_response = MagicMock()
    mock_emb_response.data = [{"embedding": _FAKE_EMBEDDING}]

    with patch("foundry.rag.retriever.litellm.embedding", return_value=mock_emb_response):
        results = retrieve("chunk text", repo, config)

    assert len(results) > 0
    assert all(isinstance(r, ScoredChunk) for r in results)


def test_retrieve_dense_only_mode(tmp_db):
    _populate_db(tmp_db)
    config = RetrieverConfig(embedding_model=_MODEL, mode="dense", top_k=3, hyde=False)
    repo = Repository(tmp_db)

    mock_emb_response = MagicMock()
    mock_emb_response.data = [{"embedding": _FAKE_EMBEDDING}]

    with patch("foundry.rag.retriever.litellm.embedding", return_value=mock_emb_response):
        results = retrieve("chunk text", repo, config)

    assert len(results) <= 3
    assert all(r.dense_rank is not None for r in results)
    assert all(r.bm25_rank is None for r in results)


def test_retrieve_bm25_only_mode(tmp_db):
    _populate_db(tmp_db)
    config = RetrieverConfig(embedding_model=_MODEL, mode="bm25", top_k=3)
    repo = Repository(tmp_db)

    results = retrieve("chunk text number", repo, config)

    assert len(results) > 0
    assert all(r.bm25_rank is not None for r in results)
    assert all(r.dense_rank is None for r in results)


def test_retrieve_with_hyde_uses_hypothesis_for_embedding(tmp_db):
    _populate_db(tmp_db)
    config = RetrieverConfig(
        embedding_model=_MODEL, mode="hybrid", top_k=5, hyde=True,
        hyde_model="openai/gpt-4o-mini"
    )
    repo = Repository(tmp_db)

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "A hypothetical answer."
    mock_emb = MagicMock()
    mock_emb.data = [{"embedding": _FAKE_EMBEDDING}]

    with (
        patch("foundry.rag.retriever.litellm.completion", return_value=mock_completion),
        patch("foundry.rag.retriever.litellm.embedding", return_value=mock_emb) as emb_mock,
    ):
        results = retrieve("some query", repo, config)

    # Embedding called with the hypothetical answer text, not the raw query
    call_args = emb_mock.call_args
    assert call_args.kwargs["input"] == ["A hypothetical answer."]


def test_retrieve_top_k_limits_results(tmp_db):
    _populate_db(tmp_db, n=10)
    config = RetrieverConfig(embedding_model=_MODEL, mode="hybrid", top_k=3, hyde=False)
    repo = Repository(tmp_db)

    mock_emb = MagicMock()
    mock_emb.data = [{"embedding": _FAKE_EMBEDDING}]

    with patch("foundry.rag.retriever.litellm.embedding", return_value=mock_emb):
        results = retrieve("chunk text number", repo, config)

    assert len(results) <= 3
