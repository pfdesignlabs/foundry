"""Hybrid retriever: BM25 (FTS5) + dense (sqlite-vec), fused via RRF (WI_0024).

HyDE query expansion (WI_0024a):
  - litellm.completion() generates a short hypothetical answer to the query
  - The hypothetical answer is embedded with the same embedding.model as ingest
  - Raw query string is kept unchanged for BM25

Reciprocal Rank Fusion:
  score(d) = 1 / (k + rank_dense) + 1 / (k + rank_bm25)   k = 60
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import litellm

from foundry.db.models import Chunk
from foundry.db.repository import Repository
from foundry.db.vectors import model_to_slug, vec_table_name

if TYPE_CHECKING:
    pass

_RRF_K = 60


@dataclass
class RetrieverConfig:
    """Configuration for the hybrid retriever.

    Attributes:
        embedding_model: LiteLLM embedding model string (provider/model format).
        mode: Retrieval mode — 'hybrid' (BM25 + dense), 'dense', or 'bm25'.
        top_k: Maximum number of chunks to return after fusion.
        hyde: Whether to use HyDE (Hypothetical Document Embedding) query expansion.
        hyde_model: LiteLLM model used to generate the hypothetical answer for HyDE.
    """

    embedding_model: str = "openai/text-embedding-3-small"
    mode: str = "hybrid"            # hybrid | dense | bm25
    top_k: int = 10
    hyde: bool = True
    hyde_model: str = "openai/gpt-4o-mini"


@dataclass
class ScoredChunk:
    """A retrieved chunk together with its RRF fusion score and per-channel ranks.

    Attributes:
        chunk: The Chunk instance from the database.
        rrf_score: Reciprocal Rank Fusion score (higher = more relevant).
        dense_rank: 1-based rank in the dense retrieval channel (None if not retrieved).
        bm25_rank: 1-based rank in the BM25 channel (None if not retrieved).
    """

    chunk: Chunk
    rrf_score: float
    dense_rank: int | None = None
    bm25_rank: int | None = None


def retrieve(
    query: str,
    repo: Repository,
    config: RetrieverConfig,
) -> list[ScoredChunk]:
    """Run hybrid retrieval and return RRF-fused chunks, best-first.

    Raises:
        RuntimeError: If vec table for the configured embedding model does not exist.
    """
    slug = model_to_slug(config.embedding_model)
    vec_table = vec_table_name(slug)

    # Validate vec table exists for configured model
    _validate_vec_table(repo._conn, vec_table, config.embedding_model)

    if config.mode == "bm25":
        bm25_results = repo.search_fts(query, limit=config.top_k)
        return _rank_bm25_only(bm25_results)

    # Embed query (with optional HyDE expansion)
    embed_query = _build_embed_query(query, config)
    query_embedding = _embed(embed_query, config.embedding_model)

    if config.mode == "dense":
        dense_results = repo.search_vec(vec_table, query_embedding, limit=config.top_k)
        return _rank_dense_only(dense_results)

    # Hybrid: both channels
    dense_results = repo.search_vec(vec_table, query_embedding, limit=config.top_k)
    bm25_results = repo.search_fts(query, limit=config.top_k)
    return _rrf_fuse(dense_results, bm25_results, top_k=config.top_k)


# ------------------------------------------------------------------
# HyDE query expansion (WI_0024a)
# ------------------------------------------------------------------


def _build_embed_query(query: str, config: RetrieverConfig) -> str:
    """Return the query string to embed.

    If HyDE is enabled, ask the LLM for a short hypothetical answer and embed that.
    The hypothetical answer is generated with config.hyde_model but always embedded
    with config.embedding_model — never a different embedding model.
    """
    if not config.hyde:
        return query

    try:
        response = litellm.completion(
            model=config.hyde_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. Write a concise, factual answer "
                        "(1 paragraph, max 100 tokens) to the following question. "
                        "Do not ask for clarification."
                    ),
                },
                {"role": "user", "content": query},
            ],
            max_tokens=100,
            temperature=0,
        )
        hypothesis = response.choices[0].message.content or query
        return hypothesis.strip()
    except Exception:
        # HyDE failure is non-fatal — fall back to raw query
        return query


# ------------------------------------------------------------------
# Embedding
# ------------------------------------------------------------------


def _embed(text: str, model: str) -> list[float]:
    """Embed *text* using LiteLLM with the specified model."""
    response = litellm.embedding(model=model, input=[text])
    return response.data[0]["embedding"]


# ------------------------------------------------------------------
# RRF fusion
# ------------------------------------------------------------------


def _rrf_fuse(
    dense_results: list[tuple[Chunk, float]],
    bm25_results: list[tuple[Chunk, float]],
    top_k: int,
) -> list[ScoredChunk]:
    """Combine dense and BM25 ranked lists via Reciprocal Rank Fusion.

    score(d) = 1/(k + rank_dense) + 1/(k + rank_bm25)   k = 60
    """
    # Build rowid → rank maps (1-indexed)
    dense_rank: dict[int, int] = {}
    for i, (chunk, _) in enumerate(dense_results):
        if chunk.rowid is not None:
            dense_rank[chunk.rowid] = i + 1

    bm25_rank: dict[int, int] = {}
    for i, (chunk, _) in enumerate(bm25_results):
        if chunk.rowid is not None:
            bm25_rank[chunk.rowid] = i + 1

    # Collect all unique rowids
    all_rowids: set[int] = set(dense_rank) | set(bm25_rank)

    # Build scored chunks
    chunk_map: dict[int, Chunk] = {}
    for chunk, _ in dense_results:
        if chunk.rowid is not None:
            chunk_map[chunk.rowid] = chunk
    for chunk, _ in bm25_results:
        if chunk.rowid is not None and chunk.rowid not in chunk_map:
            chunk_map[chunk.rowid] = chunk

    scored: list[ScoredChunk] = []
    n_dense = len(dense_results)
    n_bm25 = len(bm25_results)

    for rowid in all_rowids:
        dr = dense_rank.get(rowid, n_dense + _RRF_K)
        br = bm25_rank.get(rowid, n_bm25 + _RRF_K)
        score = 1.0 / (_RRF_K + dr) + 1.0 / (_RRF_K + br)
        scored.append(
            ScoredChunk(
                chunk=chunk_map[rowid],
                rrf_score=score,
                dense_rank=dense_rank.get(rowid),
                bm25_rank=bm25_rank.get(rowid),
            )
        )

    scored.sort(key=lambda s: s.rrf_score, reverse=True)
    return scored[:top_k]


def _rank_dense_only(dense_results: list[tuple[Chunk, float]]) -> list[ScoredChunk]:
    return [
        ScoredChunk(chunk=chunk, rrf_score=1.0 / (_RRF_K + i + 1), dense_rank=i + 1)
        for i, (chunk, _) in enumerate(dense_results)
    ]


def _rank_bm25_only(bm25_results: list[tuple[Chunk, float]]) -> list[ScoredChunk]:
    return [
        ScoredChunk(chunk=chunk, rrf_score=1.0 / (_RRF_K + i + 1), bm25_rank=i + 1)
        for i, (chunk, _) in enumerate(bm25_results)
    ]


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def _validate_vec_table(
    conn: sqlite3.Connection, vec_table: str, model: str
) -> None:
    """Raise RuntimeError if the vec table for *model* does not exist."""
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (vec_table,),
    ).fetchone()
    if exists is None:
        raise RuntimeError(
            f"No embeddings found for model '{model}'. "
            f"Run 'foundry ingest' first to populate the vector index."
        )
