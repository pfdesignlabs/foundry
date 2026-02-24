"""Web chunker — URL scraping with SSRF protection (WI_0021b).

Security requirements:
- SSRF guard: ipaddress module blocks private/loopback/link-local ranges before
  any connection is established.
- Allowed URL schemes: https:// and http:// only.
- Content-Type whitelist: text/html and text/plain only.
- Max response body: 5 MB.
- Timeout: 30 seconds (connect + read).
- Max redirects: 3.
- shell=False / no subprocess calls.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from http.client import HTTPResponse

import html2text
from bs4 import BeautifulSoup

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker
from foundry.ingest.plaintext import PlainTextChunker

_USER_AGENT = "foundry/0.1 (+https://github.com/pfdesignlabs/foundry)"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_TIMEOUT = 30  # seconds
_MAX_REDIRECTS = 3
_ALLOWED_SCHEMES = {"https", "http"}
_ALLOWED_CONTENT_TYPES = {"text/html", "text/plain"}

# html2text converter
_h2t = html2text.HTML2Text()
_h2t.ignore_links = True
_h2t.ignore_images = True
_h2t.body_width = 0


class SsrfError(ValueError):
    """Raised when a URL resolves to a private or reserved address."""


class WebChunker(BaseChunker):
    """Fetch a URL, convert HTML/plain text to plain text, then chunk it.

    SSRF protection is applied *before* any connection is made:
    the hostname is resolved and all resulting IP addresses are checked
    against private/loopback/link-local/reserved ranges via the stdlib
    ``ipaddress`` module.

    Inherits chunk_size / overlap from BaseChunker; defaults match
    PlainTextChunker (512 tokens / 10 % overlap).
    """

    def __init__(self, chunk_size: int = 512, overlap: float = 0.10) -> None:
        super().__init__(chunk_size=chunk_size, overlap=overlap)

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        """*content* is ignored; the page at *path* (URL) is fetched."""
        text = self._fetch_and_convert(path)
        if not text.strip():
            return []
        sub = PlainTextChunker(chunk_size=self.chunk_size, overlap=self.overlap)
        return sub.chunk(source_id, text)

    # ------------------------------------------------------------------
    # Fetch pipeline
    # ------------------------------------------------------------------

    def _fetch_and_convert(self, url: str) -> str:
        """Validate, fetch, and convert *url* to plain text."""
        self._validate_scheme(url)
        self._check_ssrf(url)
        raw, content_type = self._fetch(url)
        return self._to_plain_text(raw, content_type)

    @staticmethod
    def _validate_scheme(url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise ValueError(
                f"Unsupported URL scheme '{parsed.scheme}'. Only https:// and http:// are allowed."
            )

    @staticmethod
    def _check_ssrf(url: str) -> None:
        """Resolve the hostname and block private/reserved IP ranges.

        Raises SsrfError if any resolved address is private, loopback,
        link-local, or otherwise reserved.
        """
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError(f"URL has no hostname: {url}")

        try:
            addrinfos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise ValueError(f"DNS resolution failed for '{hostname}': {exc}") from exc

        for addrinfo in addrinfos:
            addr_str = addrinfo[4][0]
            try:
                ip = ipaddress.ip_address(addr_str)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise SsrfError(
                    f"URL resolves to private address ({ip}). "
                    "Access to internal network addresses is not allowed."
                )

    @staticmethod
    def _fetch(url: str) -> tuple[bytes, str]:
        """Fetch *url* with timeout, redirect limit, size cap, and Content-Type check.

        Returns (body_bytes, content_type_without_params).
        """
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})

        # Custom opener with redirect limit
        opener = urllib.request.build_opener(
            _LimitedRedirectHandler(_MAX_REDIRECTS)
        )

        try:
            response: HTTPResponse = opener.open(request, timeout=_TIMEOUT)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to fetch URL '{url}': {exc}") from exc

        # Content-Type check
        raw_ct = response.headers.get("Content-Type", "text/html")
        ct = raw_ct.split(";")[0].strip().lower()
        if ct not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(
                f"Unsupported Content-Type '{ct}' for URL '{url}'. "
                f"Accepted: {', '.join(sorted(_ALLOWED_CONTENT_TYPES))}"
            )

        # Read with size cap
        body = response.read(_MAX_BYTES + 1)
        if len(body) > _MAX_BYTES:
            raise ValueError(
                f"Response body exceeds {_MAX_BYTES // (1024 * 1024)} MB limit for URL '{url}'."
            )

        return body, ct

    @staticmethod
    def _to_plain_text(body: bytes, content_type: str) -> str:
        """Convert *body* to plain text based on *content_type*."""
        text = body.decode("utf-8", errors="replace")
        if content_type == "text/plain":
            return text

        # HTML: strip non-content tags, then html2text
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer", "head"]):
            tag.decompose()
        return _h2t.handle(str(soup)).strip()


class _LimitedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Raise an error after more than *max_redirects* redirects."""

    def __init__(self, max_redirects: int) -> None:
        self._max_redirects = max_redirects
        self._count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._count += 1
        if self._count > self._max_redirects:
            raise RuntimeError(
                f"Too many redirects (>{self._max_redirects}) for URL '{req.full_url}'."
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)
