"""Tests for GitChunker (WI_0021)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from foundry.db.models import Chunk
from foundry.ingest.git_chunker import GitChunker, _sanitise_url


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with 2 commits and return its path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    # First commit
    (repo / "readme.md").write_text("DMX512 protocol reference.")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "Initial commit"],
                   check=True, capture_output=True)
    # Second commit
    (repo / "notes.md").write_text("Wiring guide for ESP32.")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "Add wiring notes"],
                   check=True, capture_output=True)
    return repo


# ------------------------------------------------------------------
# Tests — defaults and validation
# ------------------------------------------------------------------


def test_git_chunker_default_settings():
    chunker = GitChunker()
    assert chunker.chunk_size == 600
    assert chunker.overlap == 0.0


def test_git_is_remote_https():
    assert GitChunker._is_remote("https://github.com/user/repo")


def test_git_is_remote_http():
    assert GitChunker._is_remote("http://github.com/user/repo")


def test_git_is_remote_ssh():
    assert GitChunker._is_remote("git@github.com:user/repo.git")


def test_git_is_not_remote_local():
    assert not GitChunker._is_remote("/home/user/repos/myrepo")
    assert not GitChunker._is_remote("./relative/path")


# ------------------------------------------------------------------
# Tests — URL validation
# ------------------------------------------------------------------


def test_validate_url_https_ok():
    GitChunker._validate_url("https://github.com/user/repo")  # no exception


def test_validate_url_http_ok():
    GitChunker._validate_url("http://github.com/user/repo")  # no exception


def test_validate_url_ssh_ok():
    GitChunker._validate_url("git@github.com:user/repo.git")  # no exception


def test_validate_url_bad_scheme_raises():
    with pytest.raises(ValueError, match="scheme"):
        GitChunker._validate_url("ftp://evil.com/repo")


def test_validate_url_file_scheme_raises():
    with pytest.raises(ValueError, match="scheme"):
        GitChunker._validate_url("file:///etc/passwd")


# ------------------------------------------------------------------
# Tests — token injection (security: token never appears in logs/errors)
# ------------------------------------------------------------------


def test_inject_token_with_token(monkeypatch):
    monkeypatch.setenv("GIT_TOKEN", "mytoken123")
    result = GitChunker._inject_token("https://github.com/user/repo")
    assert "mytoken123" in result
    assert result.startswith("https://")


def test_inject_token_no_token(monkeypatch):
    monkeypatch.delenv("GIT_TOKEN", raising=False)
    url = "https://github.com/user/repo"
    assert GitChunker._inject_token(url) == url


def test_inject_token_ssh_unchanged(monkeypatch):
    monkeypatch.setenv("GIT_TOKEN", "mytoken123")
    url = "git@github.com:user/repo.git"
    # SSH URLs are not modified — token only applies to HTTPS
    assert GitChunker._inject_token(url) == url


def test_sanitise_url_removes_credentials():
    url = "https://mytoken@github.com/user/repo"
    sanitised = _sanitise_url(url)
    assert "mytoken" not in sanitised
    assert "***" in sanitised


def test_clone_error_does_not_expose_token(monkeypatch):
    """RuntimeError raised by _clone must NOT contain the GIT_TOKEN."""
    monkeypatch.setenv("GIT_TOKEN", "supersecret")
    chunker = GitChunker()
    with pytest.raises(RuntimeError) as exc_info:
        # Inject a token-embedded URL and simulate CalledProcessError
        import subprocess
        url_with_token = "https://supersecret@github.com/user/nonexistent"
        chunker._clone(url_with_token, "/tmp/fake", "https://github.com/user/nonexistent")
    assert "supersecret" not in str(exc_info.value)


# ------------------------------------------------------------------
# Tests — local repo chunking
# ------------------------------------------------------------------


def test_chunk_local_returns_chunks(tmp_path):
    repo = _make_git_repo(tmp_path)
    chunker = GitChunker()
    chunks = chunker.chunk("src-1", "", path=str(repo))
    assert isinstance(chunks, list)
    assert len(chunks) == 2
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_local_source_id_set(tmp_path):
    repo = _make_git_repo(tmp_path)
    chunks = GitChunker().chunk("my-source", "", path=str(repo))
    assert all(c.source_id == "my-source" for c in chunks)


def test_chunk_local_index_sequential(tmp_path):
    repo = _make_git_repo(tmp_path)
    chunks = GitChunker().chunk("src-1", "", path=str(repo))
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_local_text_contains_commit_info(tmp_path):
    repo = _make_git_repo(tmp_path)
    chunks = GitChunker().chunk("src-1", "", path=str(repo))
    texts = " ".join(c.text for c in chunks)
    assert "wiring notes" in texts.lower() or "initial" in texts.lower()


def test_chunk_local_truncates_at_chunk_size(tmp_path):
    repo = _make_git_repo(tmp_path)
    # chunk_size=1 → char_limit=4; all commits truncated to 4 chars
    chunks = GitChunker(chunk_size=1).chunk("src-1", "", path=str(repo))
    assert all(len(c.text) <= 10 for c in chunks)  # short with small char limit


def test_chunk_local_invalid_path_raises():
    with pytest.raises(ValueError, match="does not exist"):
        GitChunker().chunk("src-1", "", path="/nonexistent/path")


def test_chunk_local_not_git_repo_raises(tmp_path):
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()
    with pytest.raises(ValueError, match="Not a git repository"):
        GitChunker().chunk("src-1", "", path=str(non_repo))


# ------------------------------------------------------------------
# Tests — remote (mocked subprocess)
# ------------------------------------------------------------------


def test_chunk_remote_validates_url():
    with pytest.raises(ValueError, match="scheme"):
        GitChunker().chunk("src-1", "", path="ftp://bad.com/repo")


def test_chunk_remote_clones_and_extracts(tmp_path, monkeypatch):
    """Remote path: mock clone, then run real git log/show on a local repo."""
    repo = _make_git_repo(tmp_path)

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        # Intercept "git clone" → copy repo to tmpdir instead of real clone
        if cmd[1] == "clone":
            tmpdir = cmd[-1]
            import shutil
            shutil.copytree(str(repo / ".git"), str(Path(tmpdir) / ".git"))
            # Make the copied repo usable
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        return original_run(cmd, **kwargs)

    monkeypatch.setattr("foundry.ingest.git_chunker.subprocess.run", fake_run)
    monkeypatch.delenv("GIT_TOKEN", raising=False)

    chunks = GitChunker().chunk("src-1", "", path="https://github.com/fake/repo")
    assert len(chunks) >= 1
