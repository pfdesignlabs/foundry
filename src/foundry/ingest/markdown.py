"""Markdown chunker — heading-aware splits with fixed-window fallback (WI_0016)."""

from __future__ import annotations

import re

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker

# Matches H1, H2, H3 headings at the start of a line.
_HEADING_RE = re.compile(r"^#{1,3} .+", re.MULTILINE)


class MarkdownChunker(BaseChunker):
    """Split Markdown on H1/H2/H3 heading boundaries.

    Strategy:
    - Find all H1/H2/H3 headings in the document.
    - Each heading + its following content is a *section*.
    - Content before the first heading (preamble) becomes its own chunk.
    - Sections that exceed ``chunk_size`` tokens are further split with
      ``_split_fixed_window()``.
    - If the document has no H1/H2/H3 headings, fall back to fixed-window
      splitting (same as PlainTextChunker).
    """

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        if not content.strip():
            return []

        sections = self._split_on_headings(content)
        if not sections:
            # Fallback: no headings → fixed window
            return self._make_chunks(source_id, self._split_fixed_window(content))

        texts: list[str] = []
        for section in sections:
            if self.count_tokens(section) <= self.chunk_size:
                texts.append(section)
            else:
                texts.extend(self._split_fixed_window(section))

        texts = [t for t in texts if t.strip()]
        return self._make_chunks(source_id, texts)

    def _split_on_headings(self, content: str) -> list[str]:
        """Split *content* on H1/H2/H3 boundaries.

        Returns an empty list if no headings are found (signals fallback).
        """
        matches = list(_HEADING_RE.finditer(content))
        if not matches:
            return []

        sections: list[str] = []

        # Preamble: content before the first heading
        if matches[0].start() > 0:
            preamble = content[: matches[0].start()].strip()
            if preamble:
                sections.append(preamble)

        # Each heading + its body
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section = content[start:end].strip()
            if section:
                sections.append(section)

        return sections
