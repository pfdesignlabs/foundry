"""Tests for context assembler (WI_0025)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from foundry.db.models import Chunk
from foundry.rag.assembler import (
    AssemblerConfig,
    AssembledContext,
    ConflictReport,
    _apply_token_budget,
    _detect_conflicts,
    _parse_conflicts,
    _parse_score_array,
    _score_chunks,
    assemble,
)
from foundry.rag.retriever import ScoredChunk


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _sc(rowid: int, text: str = "chunk text") -> ScoredChunk:
    chunk = Chunk(
        source_id=f"src-{rowid}",
        chunk_index=0,
        text=text,
        rowid=rowid,
    )
    return ScoredChunk(chunk=chunk, rrf_score=1.0 / (60 + rowid))


def _chunk(rowid: int, source_id: str = "src", text: str = "text") -> Chunk:
    return Chunk(source_id=source_id, chunk_index=rowid, text=text, rowid=rowid)


# ------------------------------------------------------------------
# _parse_score_array
# ------------------------------------------------------------------


def test_parse_score_array_valid():
    assert _parse_score_array("[8, 5, 2]", 3) == [8, 5, 2]


def test_parse_score_array_clamps_values():
    assert _parse_score_array("[12, -3, 7]", 3) == [10, 0, 7]


def test_parse_score_array_wrong_length_fallback():
    result = _parse_score_array("[8, 5]", 3)
    assert result == [10, 10, 10]


def test_parse_score_array_invalid_json_fallback():
    result = _parse_score_array("not json at all", 2)
    assert result == [10, 10]


def test_parse_score_array_embedded_in_text():
    raw = 'Here are scores: [7, 3, 9] for the chunks.'
    assert _parse_score_array(raw, 3) == [7, 3, 9]


# ------------------------------------------------------------------
# _parse_conflicts
# ------------------------------------------------------------------


def test_parse_conflicts_valid():
    raw = json.dumps([
        {"source_a": "A", "source_b": "B", "description": "They contradict."}
    ])
    result = _parse_conflicts(raw)
    assert len(result) == 1
    assert result[0].source_a == "A"
    assert result[0].description == "They contradict."


def test_parse_conflicts_empty_array():
    assert _parse_conflicts("[]") == []


def test_parse_conflicts_invalid_json():
    assert _parse_conflicts("broken") == []


def test_parse_conflicts_missing_keys_skipped():
    raw = json.dumps([{"source_a": "A"}])  # missing source_b and description
    result = _parse_conflicts(raw)
    assert len(result) == 1
    assert result[0].source_b == ""
    assert result[0].description == ""


# ------------------------------------------------------------------
# _score_chunks
# ------------------------------------------------------------------


def test_score_chunks_returns_paired_list():
    candidates = [_sc(1), _sc(2), _sc(3)]
    mock_resp = "[8, 3, 6]"

    with patch("foundry.rag.assembler.complete", return_value=mock_resp):
        result = _score_chunks("query", candidates, AssemblerConfig())

    assert len(result) == 3
    assert result[0][1] == 8
    assert result[1][1] == 3
    assert result[2][1] == 6


def test_score_chunks_llm_failure_defaults_to_ten():
    candidates = [_sc(1), _sc(2)]

    with patch("foundry.rag.assembler.complete", side_effect=Exception("API down")):
        result = _score_chunks("query", candidates, AssemblerConfig())

    assert all(score == 10 for _, score in result)


def test_score_chunks_empty_candidates():
    result = _score_chunks("query", [], AssemblerConfig())
    assert result == []


# ------------------------------------------------------------------
# _detect_conflicts
# ------------------------------------------------------------------


def test_detect_conflicts_returns_reports():
    chunks = [_chunk(1, "s1", "VCC = 3.3V"), _chunk(2, "s2", "VCC = 5V")]
    conflict_json = json.dumps([
        {"source_a": "s1", "source_b": "s2", "description": "VCC mismatch"}
    ])

    with patch("foundry.rag.assembler.complete", return_value=conflict_json):
        result = _detect_conflicts(chunks, AssemblerConfig())

    assert len(result) == 1
    assert "VCC" in result[0].description


def test_detect_conflicts_single_chunk_skips_llm():
    with patch("foundry.rag.assembler.complete") as mock_c:
        result = _detect_conflicts([_chunk(1)], AssemblerConfig())
    mock_c.assert_not_called()
    assert result == []


def test_detect_conflicts_llm_failure_returns_empty():
    chunks = [_chunk(1), _chunk(2)]
    with patch("foundry.rag.assembler.complete", side_effect=Exception("fail")):
        result = _detect_conflicts(chunks, AssemblerConfig())
    assert result == []


# ------------------------------------------------------------------
# _apply_token_budget
# ------------------------------------------------------------------


def test_apply_token_budget_fills_to_limit():
    # Each chunk ~100 chars → ~25 tokens (fallback counter)
    chunks = [_chunk(i, text="a" * 100) for i in range(10)]

    with patch("foundry.rag.assembler.count_tokens", return_value=100):
        selected, total = _apply_token_budget(chunks, "openai/gpt-4o", budget=350)

    assert len(selected) == 3  # 3 × 100 = 300 ≤ 350; 4 × 100 = 400 > 350
    assert total == 300


def test_apply_token_budget_returns_all_if_fits():
    chunks = [_chunk(i, text="short") for i in range(5)]

    with patch("foundry.rag.assembler.count_tokens", return_value=10):
        selected, total = _apply_token_budget(chunks, "openai/gpt-4o", budget=1000)

    assert len(selected) == 5
    assert total == 50


def test_apply_token_budget_empty_chunks():
    selected, total = _apply_token_budget([], "openai/gpt-4o", budget=1000)
    assert selected == []
    assert total == 0


# ------------------------------------------------------------------
# assemble() — integration
# ------------------------------------------------------------------


def test_assemble_filters_below_threshold():
    candidates = [_sc(1, "relevant"), _sc(2, "irrelevant")]
    score_resp = "[8, 2]"  # chunk 2 below threshold=4

    with (
        patch("foundry.rag.assembler.complete", side_effect=[score_resp, "[]"]),
        patch("foundry.rag.assembler.count_tokens", return_value=10),
    ):
        ctx = assemble("query", candidates, AssemblerConfig(relevance_threshold=4))

    rowids = [c.rowid for c in ctx.chunks]
    assert 1 in rowids
    assert 2 not in rowids


def test_assemble_returns_empty_if_all_filtered():
    candidates = [_sc(1)]
    score_resp = "[1]"  # below threshold

    with patch("foundry.rag.assembler.complete", return_value=score_resp):
        ctx = assemble("query", candidates, AssemblerConfig(relevance_threshold=4))

    assert ctx.chunks == []


def test_assemble_reports_conflicts():
    candidates = [_sc(1, "VCC=3.3"), _sc(2, "VCC=5")]
    score_resp = "[9, 8]"
    conflict_resp = json.dumps([
        {"source_a": "src-1", "source_b": "src-2", "description": "VCC mismatch"}
    ])

    with (
        patch("foundry.rag.assembler.complete", side_effect=[score_resp, conflict_resp]),
        patch("foundry.rag.assembler.count_tokens", return_value=5),
    ):
        ctx = assemble("query", candidates, AssemblerConfig())

    assert len(ctx.conflicts) == 1
    assert ctx.conflicts[0].description == "VCC mismatch"


def test_assemble_respects_token_budget():
    candidates = [_sc(i) for i in range(10)]
    score_resp = "[9] * 10"  # intentionally invalid → all 10
    # Use fallback all-10 scoring

    with (
        patch("foundry.rag.assembler.complete", side_effect=[
            "[9, 9, 9, 9, 9, 9, 9, 9, 9, 9]",
            "[]",  # no conflicts
        ]),
        patch("foundry.rag.assembler.count_tokens", return_value=100),
    ):
        ctx = assemble(
            "query", candidates, AssemblerConfig(token_budget=250)
        )

    # 2 × 100 = 200 ≤ 250; 3 × 100 = 300 > 250
    assert len(ctx.chunks) == 2
    assert ctx.total_tokens == 200


def test_assemble_empty_candidates():
    ctx = assemble("query", [], AssemblerConfig())
    assert ctx.chunks == []
    assert ctx.conflicts == []
    assert ctx.total_tokens == 0


def test_assemble_scores_stored_in_context():
    candidates = [_sc(1), _sc(2)]
    score_resp = "[7, 5]"

    with (
        patch("foundry.rag.assembler.complete", side_effect=[score_resp, "[]"]),
        patch("foundry.rag.assembler.count_tokens", return_value=5),
    ):
        ctx = assemble("query", candidates, AssemblerConfig())

    assert ctx.relevance_scores.get(1) == 7
    assert ctx.relevance_scores.get(2) == 5
