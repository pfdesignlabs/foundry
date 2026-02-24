"""Audio chunker — Whisper transcription via LiteLLM (WI_0021c).

Security / safety:
- File size checked BEFORE any API call: > 25 MB → hard fail.
- Only supported audio extensions are accepted.
- API key absence detected early with clear error message.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import litellm

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker
from foundry.ingest.plaintext import PlainTextChunker

_SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".webm"}
_MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB
_WHISPER_MODEL = "openai/whisper-1"

# Approximate cost for Whisper-1: $0.006 per minute.
# Rough estimate: file size in bytes / 1_000_000 ≈ minutes.
_COST_PER_MB = 0.006


class AudioChunker(BaseChunker):
    """Transcribe an audio file via OpenAI Whisper (LiteLLM) and chunk the transcript.

    Pipeline:
    1. Validate file extension and size (> 25 MB → hard fail).
    2. Show a cost estimate; prompt for confirmation unless *yes* is True.
    3. Call ``litellm.transcription(model=_WHISPER_MODEL, file=...)``.
    4. Pass transcript text to :class:`PlainTextChunker` (default 512 tokens / 10 % overlap).

    The *path* argument to ``chunk()`` must be the file path.
    *content* is ignored.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        overlap: float = 0.10,
        model: str = _WHISPER_MODEL,
        yes: bool = False,
    ) -> None:
        super().__init__(chunk_size=chunk_size, overlap=overlap)
        self.model = model
        self.yes = yes

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        """Transcribe *path* and chunk the resulting transcript."""
        self._validate_path(path)

        if not self.yes:
            self._show_cost_estimate(path)

        transcript = self._transcribe(path)
        if not transcript.strip():
            return []

        sub = PlainTextChunker(chunk_size=self.chunk_size, overlap=self.overlap)
        chunks = sub.chunk(source_id, transcript)

        # Annotate each chunk with audio metadata
        extension = Path(path).suffix.lower()
        meta = json.dumps({"source_type": "audio", "format": extension})
        for chunk in chunks:
            chunk.metadata = meta

        return chunks

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_path(path: str) -> None:
        """Raise ValueError for unsupported extensions or oversized files."""
        p = Path(path)
        ext = p.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format '{ext}'. "
                f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
            )

        try:
            size = os.path.getsize(path)
        except OSError as exc:
            raise ValueError(f"Cannot access audio file '{path}': {exc}") from exc

        if size > _MAX_FILE_BYTES:
            raise ValueError(
                f"Audio file '{path}' exceeds the 25 MB limit "
                f"({size / (1024 * 1024):.1f} MB). "
                "Split the file and ingest each part separately."
            )

    # ------------------------------------------------------------------
    # Cost estimate
    # ------------------------------------------------------------------

    @staticmethod
    def _show_cost_estimate(path: str) -> None:
        """Print cost estimate and prompt for confirmation."""
        size_mb = os.path.getsize(path) / (1024 * 1024)
        approx_minutes = size_mb  # 1 MB ≈ 1 minute (rough)
        approx_cost = approx_minutes * _COST_PER_MB

        print(f"\nTranscribing: {Path(path).name}")
        print(f"  Duration estimate: ~{approx_minutes:.0f} min  (based on file size / ~1MB/min)")
        print(f"  Estimated cost: ~${approx_cost:.3f}  (whisper-1: $0.006/min)")

        answer = input("Continue? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            raise SystemExit("Transcription cancelled.")

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def _transcribe(self, path: str) -> str:
        """Call litellm.transcription() and return the transcript text."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "No OpenAI API key found. Set the OPENAI_API_KEY environment variable."
            )

        with open(path, "rb") as audio_file:
            response = litellm.transcription(model=self.model, file=audio_file)

        return response.text or ""
