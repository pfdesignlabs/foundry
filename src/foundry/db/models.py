"""Domain models for the Foundry database layer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Source:
    id: str
    path: str
    content_hash: str
    embedding_model: str
    ingested_at: str | None = None


@dataclass
class Chunk:
    source_id: str
    chunk_index: int
    text: str
    context_prefix: str = ""
    metadata: str = field(default_factory=lambda: "{}")
    created_at: str | None = None
    rowid: int | None = None  # set after insert; None for unsaved chunks

    @property
    def metadata_dict(self) -> dict:
        return json.loads(self.metadata)
