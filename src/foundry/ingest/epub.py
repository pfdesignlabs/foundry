"""EPUB chunker — chapter-based extraction via zipfile + bs4 + html2text (WI_0018).

License note: html2text is GPL-3.0; Foundry is an internal tool so GPL-3.0 is
acceptable. ebooklib (AGPL-3.0) is NOT used.
"""

from __future__ import annotations

import warnings
import zipfile
from pathlib import Path

import html2text
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Suppress XMLParsedAsHTMLWarning: we intentionally use html.parser for OPF/container XML
# because lxml is not a Foundry dependency. html.parser handles these simple XML files fine.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from foundry.db.models import Chunk
from foundry.ingest.base import BaseChunker

# html2text converter — shared instance, thread-safe for read operations
_h2t = html2text.HTML2Text()
_h2t.ignore_links = True
_h2t.ignore_images = True
_h2t.body_width = 0  # no line wrapping


def _html_to_text(html: str) -> str:
    """Strip HTML markup and return plain text via html2text."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    cleaned_html = str(soup)
    return _h2t.handle(cleaned_html).strip()


class EpubChunker(BaseChunker):
    """Split an EPUB document into chunks per HTML chapter file.

    Strategy:
    - Open the EPUB (ZIP archive) with stdlib ``zipfile``.
    - Read ``META-INF/container.xml`` to locate the OPF package file.
    - Parse the OPF ``<spine>`` to get chapter order from ``<itemref>`` elements.
    - Convert each chapter HTML to plain text via ``beautifulsoup4`` + ``html2text``.
    - If a chapter exceeds ``chunk_size`` tokens, further split with
      ``_split_fixed_window()``.

    Default: 800 tokens / 10 % overlap (per F02-INGEST spec).
    """

    def __init__(self, chunk_size: int = 800, overlap: float = 0.10) -> None:
        super().__init__(chunk_size=chunk_size, overlap=overlap)

    def chunk(self, source_id: str, content: str, path: str = "") -> list[Chunk]:
        """*content* is ignored; the EPUB is read directly from *path*."""
        chapter_texts = self._extract_chapters(path)
        texts: list[str] = []
        for chapter in chapter_texts:
            if self.count_tokens(chapter) <= self.chunk_size:
                texts.append(chapter)
            else:
                texts.extend(self._split_fixed_window(chapter))
        texts = [t for t in texts if t.strip()]
        return self._make_chunks(source_id, texts)

    @staticmethod
    def _extract_chapters(path: str) -> list[str]:
        """Return ordered list of chapter plain-text strings from the EPUB."""
        chapters: list[str] = []
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())

            # 1. Locate OPF via META-INF/container.xml
            opf_path = EpubChunker._find_opf_path(zf, names)

            # 2. Parse OPF to get spine order → list of href paths
            hrefs = EpubChunker._parse_opf_spine(zf, opf_path, names)

            # 3. Extract and convert each chapter
            opf_dir = str(Path(opf_path).parent)
            for href in hrefs:
                full_path = f"{opf_dir}/{href}".lstrip("/") if opf_dir != "." else href
                if full_path not in names:
                    # Try without the OPF directory prefix
                    full_path = href
                if full_path not in names:
                    continue
                html = zf.read(full_path).decode("utf-8", errors="replace")
                text = _html_to_text(html)
                if text.strip():
                    chapters.append(text)

        return chapters

    @staticmethod
    def _find_opf_path(zf: zipfile.ZipFile, names: set[str]) -> str:
        """Find the OPF package file path from META-INF/container.xml."""
        if "META-INF/container.xml" in names:
            xml = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
            soup = BeautifulSoup(xml, "html.parser")
            rootfile = soup.find("rootfile")
            if rootfile and rootfile.get("full-path"):
                return rootfile["full-path"]
        # Fallback: first .opf file found
        for name in names:
            if name.endswith(".opf"):
                return name
        raise ValueError("No OPF package file found in EPUB archive.")

    @staticmethod
    def _parse_opf_spine(
        zf: zipfile.ZipFile, opf_path: str, names: set[str]
    ) -> list[str]:
        """Parse OPF spine to return ordered list of chapter hrefs."""
        opf_xml = zf.read(opf_path).decode("utf-8", errors="replace")
        soup = BeautifulSoup(opf_xml, "html.parser")

        # Build id → href manifest map
        manifest: dict[str, str] = {}
        for item in soup.find_all("item"):
            item_id = item.get("id", "")
            href = item.get("href", "")
            media_type = item.get("media-type", "")
            if "html" in media_type or href.endswith((".html", ".xhtml", ".htm")):
                manifest[item_id] = href

        # Walk spine itemrefs in order
        hrefs: list[str] = []
        for itemref in soup.find_all("itemref"):
            idref = itemref.get("idref", "")
            if idref in manifest:
                hrefs.append(manifest[idref])

        # Fallback: no spine — return all HTML items
        if not hrefs:
            hrefs = list(manifest.values())

        return hrefs
