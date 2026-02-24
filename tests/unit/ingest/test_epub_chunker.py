"""Tests for EpubChunker (WI_0018)."""

from __future__ import annotations

import io
import textwrap
import zipfile
from pathlib import Path

import pytest

from foundry.db.models import Chunk
from foundry.ingest.epub import EpubChunker


# ------------------------------------------------------------------
# Helpers — build minimal valid EPUB ZIPs in-memory
# ------------------------------------------------------------------

_CONTAINER_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
      </rootfiles>
    </container>
""")

_OPF_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="2.0">
      <manifest>
        {manifest_items}
      </manifest>
      <spine>
        {itemrefs}
      </spine>
    </package>
""")

_HTML_TEMPLATE = "<html><body><p>{text}</p></body></html>"


def _build_epub(chapters: dict[str, str]) -> io.BytesIO:
    """Build an in-memory EPUB ZIP with given chapter id→text mapping."""
    buf = io.BytesIO()
    manifest_items = []
    itemrefs = []

    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)

        for idx, (ch_id, text) in enumerate(chapters.items()):
            href = f"chapter{idx:02d}.xhtml"
            zf.writestr(f"OEBPS/{href}", _HTML_TEMPLATE.format(text=text))
            manifest_items.append(
                f'<item id="{ch_id}" href="{href}" media-type="application/xhtml+xml"/>'
            )
            itemrefs.append(f'<itemref idref="{ch_id}"/>')

        opf = _OPF_TEMPLATE.format(
            manifest_items="\n        ".join(manifest_items),
            itemrefs="\n        ".join(itemrefs),
        )
        zf.writestr("OEBPS/content.opf", opf)

    buf.seek(0)
    return buf


def _save_epub(chapters: dict[str, str], tmp_path: Path) -> str:
    """Write EPUB to tmp_path and return the file path string."""
    path = tmp_path / "test.epub"
    path.write_bytes(_build_epub(chapters).getvalue())
    return str(path)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_epub_default_settings():
    chunker = EpubChunker()
    assert chunker.chunk_size == 800
    assert chunker.overlap == pytest.approx(0.10)


def test_epub_chunk_returns_list_of_chunks(tmp_path):
    path = _save_epub({"ch1": "Chapter one content."}, tmp_path)
    chunker = EpubChunker()
    chunks = chunker.chunk("src-1", "", path=path)
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_epub_source_id_set(tmp_path):
    path = _save_epub({"ch1": "Content."}, tmp_path)
    chunker = EpubChunker()
    chunks = chunker.chunk("my-source", "", path=path)
    assert all(c.source_id == "my-source" for c in chunks)


def test_epub_chunk_index_sequential(tmp_path):
    # chunk_size=5 → 20 chars per window → multiple chunks per chapter
    chapters = {"ch1": "x" * 200, "ch2": "y" * 200}
    path = _save_epub(chapters, tmp_path)
    chunker = EpubChunker(chunk_size=5, overlap=0.0)
    chunks = chunker.chunk("src-1", "", path=path)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_epub_single_chapter_single_chunk(tmp_path):
    path = _save_epub({"ch1": "DMX512 protocol specification."}, tmp_path)
    chunker = EpubChunker(chunk_size=512)
    chunks = chunker.chunk("src-1", "", path=path)
    assert len(chunks) == 1
    assert "DMX512" in chunks[0].text


def test_epub_multiple_chapters(tmp_path):
    chapters = {"ch1": "Chapter one about DMX.", "ch2": "Chapter two about WiFi."}
    path = _save_epub(chapters, tmp_path)
    chunker = EpubChunker(chunk_size=512)
    chunks = chunker.chunk("src-1", "", path=path)
    assert len(chunks) == 2
    texts = " ".join(c.text for c in chunks)
    assert "DMX" in texts
    assert "WiFi" in texts


def test_epub_oversized_chapter_further_split(tmp_path):
    # chapter with 300 chars → chunk_size=5 (20 chars) → many sub-chunks
    path = _save_epub({"ch1": "word " * 60}, tmp_path)
    chunker = EpubChunker(chunk_size=5, overlap=0.0)
    chunks = chunker.chunk("src-1", "", path=path)
    assert len(chunks) > 1


def test_epub_script_tags_removed(tmp_path):
    html = "<html><body><script>alert('xss')</script><p>Real content.</p></body></html>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/chapter00.xhtml", html)
        opf = _OPF_TEMPLATE.format(
            manifest_items='<item id="ch1" href="chapter00.xhtml" media-type="application/xhtml+xml"/>',
            itemrefs='<itemref idref="ch1"/>',
        )
        zf.writestr("OEBPS/content.opf", opf)
    buf.seek(0)
    path = tmp_path / "test.epub"
    path.write_bytes(buf.getvalue())

    chunker = EpubChunker()
    chunks = chunker.chunk("src-1", "", path=str(path))
    full_text = " ".join(c.text for c in chunks)
    assert "alert" not in full_text
    assert "Real content" in full_text


def test_epub_empty_chapters_skipped(tmp_path):
    chapters = {"ch1": "", "ch2": "Actual content here."}
    path = _save_epub(chapters, tmp_path)
    chunker = EpubChunker()
    chunks = chunker.chunk("src-1", "", path=path)
    assert len(chunks) == 1
    assert "Actual content" in chunks[0].text


def test_epub_spine_order_preserved(tmp_path):
    # Spine order: ch2 before ch1 (reverse insertion order)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/chapterA.xhtml", _HTML_TEMPLATE.format(text="First in spine."))
        zf.writestr("OEBPS/chapterB.xhtml", _HTML_TEMPLATE.format(text="Second in spine."))
        opf = _OPF_TEMPLATE.format(
            manifest_items=(
                '<item id="chA" href="chapterA.xhtml" media-type="application/xhtml+xml"/>\n'
                '        <item id="chB" href="chapterB.xhtml" media-type="application/xhtml+xml"/>'
            ),
            itemrefs='<itemref idref="chA"/>\n        <itemref idref="chB"/>',
        )
        zf.writestr("OEBPS/content.opf", opf)
    buf.seek(0)
    path = tmp_path / "ordered.epub"
    path.write_bytes(buf.getvalue())

    chunker = EpubChunker()
    chunks = chunker.chunk("src-1", "", path=str(path))
    assert len(chunks) == 2
    assert "First" in chunks[0].text
    assert "Second" in chunks[1].text
