"""Tests for BaseChunker + MarkdownChunker (WI_0016)."""

from __future__ import annotations

import pytest

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker
from foundry.ingest.markdown import MarkdownChunker


# ------------------------------------------------------------------
# BaseChunker — validated via MarkdownChunker (concrete subclass)
# ------------------------------------------------------------------


def test_base_chunker_invalid_chunk_size():
    with pytest.raises(ValueError, match="chunk_size"):
        MarkdownChunker(chunk_size=0)


def test_base_chunker_invalid_overlap_negative():
    with pytest.raises(ValueError, match="overlap"):
        MarkdownChunker(overlap=-0.1)


def test_base_chunker_invalid_overlap_ge_one():
    with pytest.raises(ValueError, match="overlap"):
        MarkdownChunker(overlap=1.0)


def test_count_tokens_empty():
    # minimum is 1
    assert BaseChunker.count_tokens("") == 1


def test_count_tokens_short():
    # "hello" = 5 chars → 5 // 4 = 1, but min is 1
    assert BaseChunker.count_tokens("hello") == 1


def test_count_tokens_long():
    text = "a" * 400
    assert BaseChunker.count_tokens(text) == 100  # 400 // 4


def test_fixed_window_empty_returns_empty():
    chunker = MarkdownChunker()
    assert chunker._split_fixed_window("") == []
    assert chunker._split_fixed_window("   \n  ") == []


def test_fixed_window_short_text_single_segment():
    chunker = MarkdownChunker(chunk_size=512)
    result = chunker._split_fixed_window("Hello world")
    assert len(result) == 1
    assert result[0] == "Hello world"


def test_fixed_window_splits_long_text():
    # chunk_size=10 tokens → 40 chars per window, 10% overlap = 4 chars, step=36
    chunker = MarkdownChunker(chunk_size=10, overlap=0.10)
    text = "x" * 200
    segments = chunker._split_fixed_window(text)
    assert len(segments) > 1


def test_fixed_window_overlap_produces_repeated_chars():
    # With overlap, start of segment N+1 overlaps with end of segment N
    chunker = MarkdownChunker(chunk_size=10, overlap=0.50)  # 50% overlap
    text = "abcd" * 50  # 200 chars, window=40, overlap=20, step=20
    segments = chunker._split_fixed_window(text)
    # Check overlap: last chars of segment[0] appear at start of segment[1]
    assert len(segments) >= 2
    overlap_text = segments[0][-10:]
    assert overlap_text in segments[1]


# ------------------------------------------------------------------
# MarkdownChunker — heading-aware
# ------------------------------------------------------------------


def test_empty_content_returns_empty():
    chunker = MarkdownChunker()
    assert chunker.chunk("src-1", "") == []
    assert chunker.chunk("src-1", "   \n  ") == []


def test_chunk_returns_list_of_chunk_objects():
    chunker = MarkdownChunker()
    results = chunker.chunk("src-1", "## Section\nContent here.")
    assert isinstance(results, list)
    assert all(isinstance(c, Chunk) for c in results)


def test_source_id_set_on_all_chunks():
    chunker = MarkdownChunker()
    content = "## A\nText A\n## B\nText B"
    chunks = chunker.chunk("my-source", content)
    assert all(c.source_id == "my-source" for c in chunks)


def test_chunk_index_sequential_from_zero():
    chunker = MarkdownChunker()
    content = "## Section A\nAAA\n## Section B\nBBB\n## Section C\nCCC"
    chunks = chunker.chunk("src-1", content)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_h1_heading_splits():
    chunker = MarkdownChunker()
    content = "# Title A\nContent A\n# Title B\nContent B"
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) == 2
    assert "Title A" in chunks[0].text
    assert "Title B" in chunks[1].text


def test_h2_heading_splits():
    chunker = MarkdownChunker()
    content = "## Section A\nContent A\n## Section B\nContent B"
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) == 2
    assert "Section A" in chunks[0].text
    assert "Section B" in chunks[1].text


def test_h3_heading_splits():
    chunker = MarkdownChunker()
    content = "### Sub A\nContent A\n### Sub B\nContent B"
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) == 2
    assert "Sub A" in chunks[0].text
    assert "Sub B" in chunks[1].text


def test_mixed_heading_levels_all_split():
    chunker = MarkdownChunker()
    content = "# H1\nAAA\n## H2\nBBB\n### H3\nCCC"
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) == 3


def test_preamble_before_first_heading_is_first_chunk():
    chunker = MarkdownChunker()
    content = "Intro paragraph.\n\n## Section A\nContent A"
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) == 2
    assert "Intro paragraph" in chunks[0].text
    assert "Section A" in chunks[1].text


def test_no_headings_fallback_to_fixed_window():
    # chunk_size=10 → 40 chars window; 200 chars of text → multiple chunks
    chunker = MarkdownChunker(chunk_size=10, overlap=0.0)
    content = "word " * 40  # 200 chars, no headings
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) > 1


def test_oversized_section_further_split():
    # chunk_size=5 → 20 chars window; section with 100 chars → multiple sub-chunks
    chunker = MarkdownChunker(chunk_size=5, overlap=0.0)
    long_body = "x" * 100
    content = f"## Big Section\n{long_body}"
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) > 1


def test_h4_not_split():
    # H4+ should NOT trigger heading splits (only H1/H2/H3)
    chunker = MarkdownChunker()
    content = "#### Not a split point\nSome content here."
    chunks = chunker.chunk("src-1", content)
    # No H1/H2/H3 → fixed window fallback → single chunk for short content
    assert len(chunks) == 1


def test_chunk_text_is_stripped():
    chunker = MarkdownChunker()
    content = "## Section\n\n   Content with whitespace.   \n\n"
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) == 1
    assert not chunks[0].text.startswith(" ")
    assert not chunks[0].text.endswith(" ")


def test_single_heading_single_chunk():
    chunker = MarkdownChunker()
    content = "## Only Section\nJust one section."
    chunks = chunker.chunk("src-1", content)
    assert len(chunks) == 1
    assert "Only Section" in chunks[0].text
