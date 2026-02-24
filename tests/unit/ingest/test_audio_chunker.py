"""Tests for AudioChunker (WI_0021c)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from foundry.db.models import Chunk
from foundry.ingest.audio import AudioChunker, _MAX_FILE_BYTES, _SUPPORTED_EXTENSIONS


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _write_audio_file(tmp_path: Path, ext: str = ".mp3", size: int = 1024) -> Path:
    """Write a fake audio file of given size and return its path."""
    p = tmp_path / f"test{ext}"
    p.write_bytes(b"\x00" * size)
    return p


def _mock_transcribe(text: str):
    """Patch _transcribe to return *text* without an API call."""
    return patch.object(AudioChunker, "_transcribe", return_value=text)


# ------------------------------------------------------------------
# Tests — file validation
# ------------------------------------------------------------------


def test_supported_extensions_present():
    assert ".mp3" in _SUPPORTED_EXTENSIONS
    assert ".wav" in _SUPPORTED_EXTENSIONS
    assert ".m4a" in _SUPPORTED_EXTENSIONS
    assert ".ogg" in _SUPPORTED_EXTENSIONS
    assert ".flac" in _SUPPORTED_EXTENSIONS
    assert ".mp4" in _SUPPORTED_EXTENSIONS
    assert ".webm" in _SUPPORTED_EXTENSIONS


def test_unsupported_extension_raises(tmp_path):
    p = _write_audio_file(tmp_path, ext=".avi")
    with pytest.raises(ValueError, match="Unsupported audio format"):
        AudioChunker._validate_path(str(p))


def test_file_over_25mb_raises(tmp_path):
    p = _write_audio_file(tmp_path, size=_MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="25 MB limit"):
        AudioChunker._validate_path(str(p))


def test_file_exactly_25mb_ok(tmp_path):
    p = _write_audio_file(tmp_path, size=_MAX_FILE_BYTES)
    AudioChunker._validate_path(str(p))  # should not raise


def test_nonexistent_file_raises():
    with pytest.raises(ValueError, match="Cannot access"):
        AudioChunker._validate_path("/nonexistent/file.mp3")


# ------------------------------------------------------------------
# Tests — chunk() pipeline (mocked transcription)
# ------------------------------------------------------------------


def test_chunk_returns_list_of_chunks(tmp_path):
    p = _write_audio_file(tmp_path)
    with _mock_transcribe("DMX512 protocol timing specification."):
        chunks = AudioChunker(yes=True).chunk("src-1", "", path=str(p))
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_source_id_set(tmp_path):
    p = _write_audio_file(tmp_path)
    with _mock_transcribe("Some transcript text."):
        chunks = AudioChunker(yes=True).chunk("my-source", "", path=str(p))
    assert all(c.source_id == "my-source" for c in chunks)


def test_chunk_metadata_has_audio_source_type(tmp_path):
    p = _write_audio_file(tmp_path, ext=".wav")
    with _mock_transcribe("Transcript content."):
        chunks = AudioChunker(yes=True).chunk("src-1", "", path=str(p))
    assert len(chunks) >= 1
    meta = json.loads(chunks[0].metadata)
    assert meta["source_type"] == "audio"
    assert meta["format"] == ".wav"


def test_chunk_empty_transcript_returns_empty(tmp_path):
    p = _write_audio_file(tmp_path)
    with _mock_transcribe(""):
        chunks = AudioChunker(yes=True).chunk("src-1", "", path=str(p))
    assert chunks == []


def test_chunk_index_sequential(tmp_path):
    p = _write_audio_file(tmp_path)
    long_text = "word " * 200
    with _mock_transcribe(long_text):
        chunks = AudioChunker(chunk_size=10, overlap=0.0, yes=True).chunk("src-1", "", path=str(p))
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_yes_flag_skips_prompt(tmp_path):
    """With yes=True, no confirmation prompt is shown."""
    p = _write_audio_file(tmp_path)
    with _mock_transcribe("text"):
        # Would hang on input() without yes=True
        chunks = AudioChunker(yes=True).chunk("src-1", "", path=str(p))
    assert isinstance(chunks, list)


def test_chunk_no_api_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = _write_audio_file(tmp_path)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        AudioChunker(yes=True).chunk("src-1", "", path=str(p))


def test_transcribe_calls_litellm(tmp_path, monkeypatch):
    """_transcribe() calls litellm.transcription with the correct model."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    p = _write_audio_file(tmp_path)

    mock_response = MagicMock()
    mock_response.text = "Transcribed audio content."

    with patch("foundry.ingest.audio.litellm.transcription", return_value=mock_response) as mock_call:
        result = AudioChunker(yes=True)._transcribe(str(p))

    assert result == "Transcribed audio content."
    mock_call.assert_called_once()
    call_kwargs = mock_call.call_args
    assert call_kwargs[1]["model"] == "openai/whisper-1" or call_kwargs[0][0] == "openai/whisper-1" or "whisper" in str(call_kwargs)
