"""Embedding writer — contextual prefix generation + LiteLLM embeddings (WI_0022).

Implements D0004 (contextual embedding):
- Each chunk gets an LLM-generated context prefix before embedding.
- What is embedded: f"{context_prefix}\\n\\n{chunk_text}"
- The chunk text itself is stored unchanged in the chunks table.
- The context prefix is stored in chunks.context_prefix column.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import litellm

from foundry.db.models import Chunk
from foundry.db.repository import Repository

# Models with explicit cost tiers (for "expensive model" warning).
# Models NOT ending in -mini, -small, or known cheap identifiers are flagged.
_CHEAP_SUFFIXES = ("-mini", "-small", "-nano", ":free", "local")

_CONTEXT_PREFIX_PROMPT = """\
You are a document assistant. Write a single concise sentence (max 40 words) \
that describes the broader context of the following chunk within the document. \
This context sentence will be prepended to the chunk text before embedding \
to improve retrieval precision.

Chunk:
{chunk_text}

Context sentence:"""


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""

    model: str = "openai/text-embedding-3-small"
    context_model: str = "openai/gpt-4o-mini"
    dimensions: int = 1536


class EmbeddingWriter:
    """Write chunks to the DB with LiteLLM embeddings and contextual prefixes.

    For each chunk:
    1. Generate a context prefix via ``litellm.completion()`` (D0004).
    2. Store the chunk (with prefix in ``context_prefix`` column) via
       ``Repository.add_chunk()``.
    3. Embed ``f"{prefix}\\n\\n{chunk.text}"`` via ``litellm.embedding()``.
    4. Store the embedding via ``Repository.add_embedding()``.

    Args:
        repo:   Open Repository instance.
        config: Embedding configuration (model, context_model, dimensions).
    """

    def __init__(self, repo: Repository, config: EmbeddingConfig | None = None) -> None:
        self._repo = repo
        self._config = config or EmbeddingConfig()
        self._warn_if_expensive()

    def write(self, chunks: list[Chunk], vec_table: str) -> list[int]:
        """Embed *chunks* and persist them. Returns the list of new rowids."""
        self._check_api_key()
        rowids: list[int] = []
        for chunk in chunks:
            prefix = self._generate_prefix(chunk.text)
            chunk.context_prefix = prefix

            rowid = self._repo.add_chunk(chunk)

            embed_text = f"{prefix}\n\n{chunk.text}" if prefix.strip() else chunk.text
            embedding = self._embed(embed_text)
            self._repo.add_embedding(vec_table, rowid, embedding)

            rowids.append(rowid)
        return rowids

    # ------------------------------------------------------------------
    # Context prefix generation
    # ------------------------------------------------------------------

    def _generate_prefix(self, chunk_text: str) -> str:
        """Call litellm.completion() to generate a context prefix for *chunk_text*."""
        prompt = _CONTEXT_PREFIX_PROMPT.format(chunk_text=chunk_text[:2000])
        try:
            response = litellm.completion(
                model=self._config.context_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.0,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            # Non-fatal: fall back to empty prefix rather than aborting ingest.
            return ""

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        """Call litellm.embedding() and return the embedding vector."""
        response = litellm.embedding(model=self._config.model, input=[text])
        return response.data[0]["embedding"]

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _check_api_key(self) -> None:
        """Raise RuntimeError if no API key is available for the embedding model."""
        provider = self._config.model.split("/")[0].lower() if "/" in self._config.model else ""
        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "cohere": "COHERE_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        required_env = env_map.get(provider)
        if required_env and not os.environ.get(required_env):
            raise RuntimeError(
                f"No API key found for provider '{provider}'. "
                f"Set the {required_env} environment variable."
            )

    def _warn_if_expensive(self) -> None:
        """Warn if context_model is not a known cheap model."""
        model = self._config.context_model.lower()
        if not any(model.endswith(suffix) or suffix in model for suffix in _CHEAP_SUFFIXES):
            import warnings

            warnings.warn(
                f"context_model '{self._config.context_model}' may be expensive. "
                "Consider using 'openai/gpt-4o-mini' to reduce ingest costs.",
                UserWarning,
                stacklevel=3,
            )
