"""Tests for PdfChunker (WI_0017)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from foundry.db.models import Chunk
from foundry.ingest.pdf import PdfChunker


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _mock_reader(page_texts: list[str]):
    """Return a mock PdfReader with pages that yield the given texts."""
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    reader = MagicMock()
    reader.pages = pages
    return reader


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_pdf_chunker_default_settings():
    chunker = PdfChunker()
    assert chunker.chunk_size == 400
    assert chunker.overlap == pytest.approx(0.20)


def test_pdf_chunker_custom_settings():
    chunker = PdfChunker(chunk_size=200, overlap=0.10)
    assert chunker.chunk_size == 200


def test_pdf_chunk_returns_list_of_chunks():
    chunker = PdfChunker()
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader(["Page one content."])
        chunks = chunker.chunk("src-1", "", path="doc.pdf")
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_pdf_chunk_source_id_set():
    chunker = PdfChunker()
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader(["Content on page."])
        chunks = chunker.chunk("my-source", "", path="doc.pdf")
    assert all(c.source_id == "my-source" for c in chunks)


def test_pdf_chunk_index_sequential():
    # chunk_size=5 → 20 chars per window → many chunks from long text
    chunker = PdfChunker(chunk_size=5, overlap=0.0)
    long_text = "word " * 50  # 250 chars
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader([long_text])
        chunks = chunker.chunk("src-1", "", path="doc.pdf")
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_pdf_empty_pages_skipped():
    chunker = PdfChunker()
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader(["", "  ", "Real content here."])
        chunks = chunker.chunk("src-1", "", path="doc.pdf")
    assert len(chunks) == 1
    assert "Real content" in chunks[0].text


def test_pdf_none_page_text_skipped():
    chunker = PdfChunker()
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader([None, "Actual text."])
        chunks = chunker.chunk("src-1", "", path="doc.pdf")
    assert len(chunks) == 1


def test_pdf_all_empty_pages_returns_empty():
    chunker = PdfChunker()
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader(["", "   "])
        chunks = chunker.chunk("src-1", "", path="doc.pdf")
    assert chunks == []


def test_pdf_multiple_pages_concatenated():
    chunker = PdfChunker(chunk_size=512)
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader(["Page one.", "Page two."])
        chunks = chunker.chunk("src-1", "", path="doc.pdf")
    # Both pages fit in one chunk at 512 tokens
    assert len(chunks) == 1
    assert "Page one" in chunks[0].text
    assert "Page two" in chunks[0].text


def test_pdf_long_content_produces_multiple_chunks():
    chunker = PdfChunker(chunk_size=5, overlap=0.0)  # 20 chars per window
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader(["x" * 200])
        chunks = chunker.chunk("src-1", "", path="doc.pdf")
    assert len(chunks) > 1


def test_pdf_path_passed_to_reader():
    chunker = PdfChunker()
    with patch("foundry.ingest.pdf.pypdf") as mock_pypdf:
        mock_pypdf.PdfReader.return_value = _mock_reader(["text"])
        chunker.chunk("src-1", "", path="/data/report.pdf")
        mock_pypdf.PdfReader.assert_called_once_with("/data/report.pdf")
