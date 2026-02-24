"""Tests for WebChunker (WI_0021b) — SSRF guard, scheme validation, fetch pipeline."""

from __future__ import annotations

import ipaddress
import socket
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from foundry.db.models import Chunk
from foundry.ingest.web import SsrfError, WebChunker


# ------------------------------------------------------------------
# Scheme validation
# ------------------------------------------------------------------


def test_scheme_https_ok():
    WebChunker._validate_scheme("https://example.com/page")  # no exception


def test_scheme_http_ok():
    WebChunker._validate_scheme("http://example.com/page")  # no exception


def test_scheme_ftp_raises():
    with pytest.raises(ValueError, match="scheme"):
        WebChunker._validate_scheme("ftp://example.com")


def test_scheme_file_raises():
    with pytest.raises(ValueError, match="scheme"):
        WebChunker._validate_scheme("file:///etc/passwd")


def test_check_ssrf_no_hostname_raises():
    with pytest.raises(ValueError, match="hostname"):
        WebChunker._check_ssrf("https://")


# ------------------------------------------------------------------
# SSRF guard — _check_ssrf()
# ------------------------------------------------------------------


def _patch_getaddrinfo(ip: str):
    """Return a context manager that makes getaddrinfo resolve to *ip*."""
    addr_info = [(None, None, None, None, (ip, 0))]
    return patch("foundry.ingest.web.socket.getaddrinfo", return_value=addr_info)


def test_ssrf_public_ip_ok():
    with _patch_getaddrinfo("1.2.3.4"):
        WebChunker._check_ssrf("https://example.com")  # no exception


def test_ssrf_loopback_blocked():
    with _patch_getaddrinfo("127.0.0.1"):
        with pytest.raises(SsrfError, match="private address"):
            WebChunker._check_ssrf("http://localhost/")


def test_ssrf_private_rfc1918_blocked():
    with _patch_getaddrinfo("192.168.1.1"):
        with pytest.raises(SsrfError, match="private address"):
            WebChunker._check_ssrf("http://192.168.1.1/")


def test_ssrf_link_local_blocked():
    with _patch_getaddrinfo("169.254.169.254"):
        with pytest.raises(SsrfError, match="private address"):
            WebChunker._check_ssrf("http://169.254.169.254/latest/meta-data/")


def test_ssrf_10_x_blocked():
    with _patch_getaddrinfo("10.0.0.1"):
        with pytest.raises(SsrfError, match="private address"):
            WebChunker._check_ssrf("http://10.0.0.1/")


def test_ssrf_172_16_blocked():
    with _patch_getaddrinfo("172.16.0.1"):
        with pytest.raises(SsrfError, match="private address"):
            WebChunker._check_ssrf("http://172.16.0.1/")


def test_ssrf_ipv6_loopback_blocked():
    with _patch_getaddrinfo("::1"):
        with pytest.raises(SsrfError, match="private address"):
            WebChunker._check_ssrf("http://[::1]/")


# ------------------------------------------------------------------
# _to_plain_text()
# ------------------------------------------------------------------


def test_plain_text_passthrough():
    result = WebChunker._to_plain_text(b"Hello world.", "text/plain")
    assert "Hello world" in result


def test_html_converted_to_text():
    html = b"<html><body><p>DMX512 protocol.</p></body></html>"
    result = WebChunker._to_plain_text(html, "text/html")
    assert "DMX512" in result
    assert "<" not in result


def test_html_script_removed():
    html = b"<html><body><script>alert('xss')</script><p>Content.</p></body></html>"
    result = WebChunker._to_plain_text(html, "text/html")
    assert "alert" not in result
    assert "Content" in result


# ------------------------------------------------------------------
# chunk() — full pipeline (mocked fetch)
# ------------------------------------------------------------------


def _mock_fetch(body: bytes, content_type: str = "text/html"):
    """Patch _fetch_and_convert to return a fixed plain-text string."""

    def fake_fetch_and_convert(url):
        return WebChunker._to_plain_text(body, content_type)

    return patch.object(WebChunker, "_fetch_and_convert", side_effect=fake_fetch_and_convert)


def test_chunk_returns_list_of_chunks():
    with _mock_fetch(b"<html><body><p>DMX512 timing.</p></body></html>"):
        chunker = WebChunker()
        chunks = chunker.chunk("src-1", "", path="https://example.com")
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_source_id_set():
    with _mock_fetch(b"<p>Content here.</p>"):
        chunks = WebChunker().chunk("my-source", "", path="https://example.com")
    assert all(c.source_id == "my-source" for c in chunks)


def test_chunk_empty_page_returns_empty():
    with _mock_fetch(b"<html><body></body></html>"):
        chunks = WebChunker().chunk("src-1", "", path="https://example.com")
    assert chunks == []


def test_chunk_long_page_multiple_chunks():
    body = ("<p>" + "word " * 300 + "</p>").encode()
    with _mock_fetch(body):
        chunks = WebChunker(chunk_size=10, overlap=0.0).chunk("src-1", "", path="https://example.com")
    assert len(chunks) > 1


def test_chunk_index_sequential():
    body = ("<p>" + "word " * 300 + "</p>").encode()
    with _mock_fetch(body):
        chunks = WebChunker(chunk_size=10, overlap=0.0).chunk("src-1", "", path="https://example.com")
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
