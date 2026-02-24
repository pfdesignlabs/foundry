"""Git chunker — commits + diffs as chunks (WI_0021).

Security requirements:
- shell=False always (no command injection).
- URL scheme whitelist: https://, http://, git@ only.
- Temp dirs created with mode=0o700; cleaned via try/finally + atexit.
- GIT_TOKEN injected into URL in-memory; never logged, never in error output.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker

# URL schemes that are allowed for remote git repositories.
_ALLOWED_SCHEMES = {"https", "http"}
_GIT_SSH_PREFIX = "git@"

# Regex to sanitise clone URLs in error messages (strip credentials).
import re

_CRED_RE = re.compile(r"(https?://)([^@/]+@)", re.IGNORECASE)


def _sanitise_url(url: str) -> str:
    """Remove embedded credentials from a URL for safe logging / error messages."""
    return _CRED_RE.sub(r"\1***@", url)


class GitChunker(BaseChunker):
    """Chunk a git repository by commits.

    Each chunk contains the commit message + diff/stat output, truncated to
    ``chunk_size * 4`` characters (≈ ``chunk_size`` tokens).

    Accepts:
    - Local repository path (absolute or relative): validated as an existing
      directory containing a ``.git`` subdirectory.
    - Remote URL (``https://``, ``http://``, ``git@``): cloned to a temp dir
      with ``mode=0o700``, cleaned up via ``try/finally`` + ``atexit.register``.

    Private repos via ``GIT_TOKEN`` env var (injected into HTTPS URL).
    SSH repos via system SSH keys (``git@`` URLs).

    Default: 600 tokens / 0 % overlap (per F02-INGEST spec).
    """

    def __init__(self, chunk_size: int = 600, overlap: float = 0.0) -> None:
        super().__init__(chunk_size=chunk_size, overlap=overlap)

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        """*content* is ignored; the repo is read from *path* (local path or URL)."""
        if self._is_remote(path):
            return self._chunk_remote(source_id, path)
        return self._chunk_local(source_id, path)

    # ------------------------------------------------------------------
    # Local repo
    # ------------------------------------------------------------------

    def _chunk_local(self, source_id: str, path: str) -> list[Chunk]:
        repo_path = Path(path).resolve()
        if not repo_path.is_dir():
            raise ValueError(f"Repository path does not exist: {path}")
        if not (repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {path}")
        return self._extract_commits(source_id, str(repo_path))

    # ------------------------------------------------------------------
    # Remote repo
    # ------------------------------------------------------------------

    def _chunk_remote(self, source_id: str, url: str) -> list[Chunk]:
        self._validate_url(url)
        clone_url = self._inject_token(url)

        tmpdir = tempfile.mkdtemp()
        os.chmod(tmpdir, 0o700)
        atexit.register(_cleanup_dir, tmpdir)  # safety net for crashes

        try:
            self._clone(clone_url, tmpdir, url)
            return self._extract_commits(source_id, tmpdir)
        finally:
            _cleanup_dir(tmpdir)

    @staticmethod
    def _validate_url(url: str) -> None:
        """Raise ValueError if *url* uses a disallowed scheme."""
        if url.startswith(_GIT_SSH_PREFIX):
            return  # git@ SSH — allowed
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise ValueError(
                f"Unsupported URL scheme '{parsed.scheme}'. "
                f"Allowed: https://, http://, git@"
            )

    @staticmethod
    def _inject_token(url: str) -> str:
        """Inject GIT_TOKEN into an HTTPS/HTTP URL for private repo auth.

        The token is taken from the ``GIT_TOKEN`` environment variable.
        The modified URL is only used for the git clone call and is never
        logged or included in exception messages.
        """
        token = os.environ.get("GIT_TOKEN", "")
        if not token or not url.startswith(("https://", "http://")):
            return url
        parsed = urllib.parse.urlparse(url)
        netloc_with_token = f"{token}@{parsed.netloc}"
        return parsed._replace(netloc=netloc_with_token).geturl()

    @staticmethod
    def _clone(clone_url: str, tmpdir: str, original_url: str) -> None:
        """Run git clone (shell=False). Raises RuntimeError on failure.

        *original_url* (without credentials) is used in error messages.
        """
        try:
            subprocess.run(
                ["git", "clone", "--", clone_url, tmpdir],
                shell=False,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            # Strip credentials from stderr before surfacing in error message.
            stderr_safe = _sanitise_url(exc.stderr or "")
            raise RuntimeError(
                f"git clone failed for {_sanitise_url(original_url)}: {stderr_safe}"
            ) from None

    # ------------------------------------------------------------------
    # Commit extraction
    # ------------------------------------------------------------------

    def _extract_commits(self, source_id: str, repo_path: str) -> list[Chunk]:
        """Return chunks — one per commit — for the repo at *repo_path*."""
        hashes = self._get_commit_hashes(repo_path)
        char_limit = self.chunk_size * 4
        texts: list[str] = []
        for commit_hash in hashes:
            text = self._get_commit_text(repo_path, commit_hash)
            if text:
                if len(text) > char_limit:
                    text = text[:char_limit]
                texts.append(text.strip())
        return self._make_chunks(source_id, texts)

    @staticmethod
    def _get_commit_hashes(repo_path: str) -> list[str]:
        result = subprocess.run(
            ["git", "log", "--format=%H", "--no-merges"],
            cwd=repo_path,
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        )
        return [h.strip() for h in result.stdout.splitlines() if h.strip()]

    @staticmethod
    def _get_commit_text(repo_path: str, commit_hash: str) -> str:
        """Return formatted commit message + diff --stat for *commit_hash*."""
        result = subprocess.run(
            ["git", "show", "--stat", f"--format=commit %H%n%nAuthor: %an <%ae>%nDate: %ad%n%nSubject: %s%n%n%b", commit_hash],
            cwd=repo_path,
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    # ------------------------------------------------------------------
    # URL detection helper
    # ------------------------------------------------------------------

    @staticmethod
    def _is_remote(path: str) -> bool:
        # Any path with a :// scheme or git@ prefix is treated as remote.
        # Unknown schemes are caught by _validate_url() inside _chunk_remote().
        return "://" in path or path.startswith(_GIT_SSH_PREFIX)


def _cleanup_dir(path: str) -> None:
    """Remove a directory tree, ignoring errors (used as atexit handler)."""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass
