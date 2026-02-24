"""PDF chunker — page-based extraction via pypdf (WI_0017)."""

from __future__ import annotations

import pypdf

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker


class PdfChunker(BaseChunker):
    """Split a PDF document into chunks using pypdf.

    Strategy:
    - Extract text page-by-page via ``pypdf.PdfReader``.
    - Concatenate all page text into a single string, then apply the
      fixed-window splitter (same algorithm as PlainTextChunker).
    - Pages that yield no text (scanned images, etc.) are silently skipped.

    Default: 400 tokens / 20 % overlap (per F02-INGEST spec).
    """

    def __init__(self, chunk_size: int = 400, overlap: float = 0.20) -> None:
        super().__init__(chunk_size=chunk_size, overlap=overlap)

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        """*content* is ignored; the PDF is read directly from *path*."""
        text = self._extract_text(path)
        if not text.strip():
            return []
        segments = self._split_fixed_window(text)
        return self._make_chunks(source_id, segments)

    @staticmethod
    def _extract_text(path: str) -> str:
        """Extract all page text from the PDF at *path*."""
        reader = pypdf.PdfReader(path)
        parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            stripped = page_text.strip()
            if stripped:
                parts.append(stripped)
        return "\n\n".join(parts)
