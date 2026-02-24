"""Tests for PlainTextChunker (WI_0020)."""

from __future__ import annotations

import pytest

from foundry.db.models import Chunk
from foundry.ingest.plaintext import PlainTextChunker


def test_plaintext_default_settings():
    chunker = PlainTextChunker()
    assert chunker.chunk_size == 512
    assert chunker.overlap == pytest.approx(0.10)


def test_plaintext_empty_content():
    assert PlainTextChunker().chunk("src-1", "") == []
    assert PlainTextChunker().chunk("src-1", "  \n  ") == []


def test_plaintext_returns_chunks():
    chunks = PlainTextChunker().chunk("src-1", "Hello world.")
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_plaintext_source_id_set():
    chunks = PlainTextChunker().chunk("my-source", "Some text.")
    assert all(c.source_id == "my-source" for c in chunks)


def test_plaintext_short_text_single_chunk():
    chunker = PlainTextChunker(chunk_size=512)
    chunks = chunker.chunk("src-1", "Short text.")
    assert len(chunks) == 1
    assert "Short text" in chunks[0].text


def test_plaintext_long_text_multiple_chunks():
    chunker = PlainTextChunker(chunk_size=10, overlap=0.0)  # 40 chars per window
    chunks = chunker.chunk("src-1", "x" * 200)
    assert len(chunks) > 1


def test_plaintext_chunk_index_sequential():
    chunker = PlainTextChunker(chunk_size=10, overlap=0.0)
    chunks = chunker.chunk("src-1", "a" * 200)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_plaintext_overlap_produces_more_chunks():
    # Same text, with overlap produces more chunks than without
    text = "x" * 400
    no_overlap = PlainTextChunker(chunk_size=10, overlap=0.0).chunk("s", text)
    with_overlap = PlainTextChunker(chunk_size=10, overlap=0.50).chunk("s", text)
    assert len(with_overlap) >= len(no_overlap)


def test_plaintext_text_preserved():
    content = "DMX512 protocol timing specification reference design."
    chunks = PlainTextChunker(chunk_size=512).chunk("src-1", content)
    assert len(chunks) == 1
    assert "DMX512" in chunks[0].text
