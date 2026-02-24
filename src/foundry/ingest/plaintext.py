"""Plain text chunker — fixed window with overlap (WI_0020)."""

from __future__ import annotations

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker


class PlainTextChunker(BaseChunker):
    """Split plain text into fixed-size windows with overlap.

    Default: 512 tokens / 10 % overlap (per F02-INGEST spec).
    Delegates entirely to ``BaseChunker._split_fixed_window()``.
    """

    def __init__(self, chunk_size: int = 512, overlap: float = 0.10) -> None:
        super().__init__(chunk_size=chunk_size, overlap=overlap)

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        if not content.strip():
            return []
        segments = self._split_fixed_window(content)
        return self._make_chunks(source_id, segments)
