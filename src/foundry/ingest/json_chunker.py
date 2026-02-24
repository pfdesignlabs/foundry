"""JSON chunker — object-based splits for arrays and flat dicts (WI_0019)."""

from __future__ import annotations

import json

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker


class JsonChunker(BaseChunker):
    """Split a JSON document into chunks.

    Supported top-level shapes:
    - **Array of objects** ``[{...}, {...}]``: each object serialised to a
      JSON string becomes a candidate segment. Adjacent objects are grouped
      until the accumulated text exceeds ``chunk_size`` tokens.
    - **Flat dict / nested object** ``{...}``: each top-level key-value pair
      is serialised as ``"key": value`` and grouped similarly.
    - **Array of scalars** ``[1, 2, 3]``: items are grouped by token budget.
    - **Scalar** (string, number, bool, null): treated as a single chunk.

    Default: 300 tokens per chunk, 0 % overlap (per F02-INGEST spec).
    """

    def __init__(self, chunk_size: int = 300, overlap: float = 0.0) -> None:
        super().__init__(chunk_size=chunk_size, overlap=overlap)

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        if not content.strip():
            return []

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Not valid JSON — fall back to plain-text fixed window
            return self._make_chunks(source_id, self._split_fixed_window(content))

        segments = self._segment(data)
        return self._make_chunks(source_id, segments)

    def _segment(self, data: object) -> list[str]:
        """Convert JSON data into a list of text segments."""
        if isinstance(data, list):
            return self._group_items(
                [json.dumps(item, ensure_ascii=False, indent=None) for item in data]
            )
        if isinstance(data, dict):
            pairs = [
                f'"{k}": {json.dumps(v, ensure_ascii=False)}'
                for k, v in data.items()
            ]
            return self._group_items(pairs)
        # Scalar (str, int, float, bool, None)
        return [json.dumps(data, ensure_ascii=False)]

    def _group_items(self, items: list[str]) -> list[str]:
        """Group serialised items into chunks that fit within chunk_size tokens."""
        segments: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for item in items:
            item_tokens = self.count_tokens(item)
            if current_parts and current_tokens + item_tokens > self.chunk_size:
                segments.append("\n".join(current_parts))
                current_parts = []
                current_tokens = 0
            current_parts.append(item)
            current_tokens += item_tokens

        if current_parts:
            segments.append("\n".join(current_parts))

        return [s for s in segments if s.strip()]
