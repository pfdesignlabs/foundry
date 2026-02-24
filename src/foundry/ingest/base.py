"""Base chunker interface for all Foundry source types (WI_0016)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from foundry.db.models import Chunk


class BaseChunker(ABC):
    """Abstract base for all chunkers.

    Subclasses implement ``chunk()`` and may use ``_split_fixed_window()``
    and ``_make_chunks()`` for the fixed-window fallback path.

    Token counting uses a 4-chars-per-token approximation; no external
    tokenizer dependency is required.
    """

    def __init__(self, chunk_size: int = 512, overlap: float = 0.10) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if not 0.0 <= overlap < 1.0:
            raise ValueError("overlap must be in [0.0, 1.0)")
        self.chunk_size = chunk_size
        self.overlap = overlap

    @abstractmethod
    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        """Split *content* into Chunk objects for *source_id*.

        Args:
            source_id: UUID of the parent Source row.
            content: Full decoded text of the source document.
            path: Original file path (used for metadata / error messages).

        Returns:
            Ordered list of Chunk objects with sequential ``chunk_index``.
        """

    @staticmethod
    def count_tokens(text: str) -> int:
        """Approximate token count: 4 characters ≈ 1 token.

        Fast, dependency-free approximation consistent with GPT tokeniser
        averages for English prose and technical documentation.
        """
        return max(1, len(text) // 4)

    def _split_fixed_window(self, text: str) -> list[str]:
        """Split *text* into fixed-window segments with overlap.

        Window size = ``self.chunk_size * 4`` characters.
        Overlap     = ``self.overlap`` fraction of window size.
        Segments are stripped; empty segments are omitted.
        """
        if not text.strip():
            return []

        char_size = self.chunk_size * 4
        overlap_chars = int(char_size * self.overlap)
        step = max(1, char_size - overlap_chars)

        segments: list[str] = []
        pos = 0
        length = len(text)

        while pos < length:
            end = min(pos + char_size, length)
            segment = text[pos:end].strip()
            if segment:
                segments.append(segment)
            if end >= length:
                break
            pos += step

        return segments

    def _make_chunks(self, source_id: str, texts: list[str]) -> list[Chunk]:
        """Convert a list of text strings into sequentially indexed Chunks."""
        return [
            Chunk(source_id=source_id, chunk_index=i, text=t)
            for i, t in enumerate(texts)
        ]
