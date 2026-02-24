"""foundry ingest — ingest sources into .foundry.db (WI_0023).

Source dispatch by extension / URL scheme:
  https:// / http://  → WebChunker (or GitChunker if github.com / .git)
  git@               → GitChunker
  .pdf               → PdfChunker
  .epub              → EpubChunker
  .md / .markdown    → MarkdownChunker
  .json              → JsonChunker
  .txt .rst .text .csv .log → PlainTextChunker
  .mp3 .wav .m4a .ogg .flac .mp4 .webm → AudioChunker
  directory          → expanded to individual files (--recursive for subdirs)
"""

from __future__ import annotations

import fnmatch
import hashlib
import sqlite3
import uuid
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from foundry.db.connection import Database
from foundry.db.models import Source
from foundry.db.repository import Repository
from foundry.db.schema import initialize
from foundry.db.vectors import ensure_vec_table, model_to_slug
from foundry.ingest.audio import AudioChunker
from foundry.ingest.audio import _SUPPORTED_EXTENSIONS as _AUDIO_EXTS
from foundry.ingest.base import BaseChunker
from foundry.ingest.embedding_writer import EmbeddingConfig, EmbeddingWriter
from foundry.ingest.epub import EpubChunker
from foundry.ingest.git_chunker import GitChunker
from foundry.ingest.json_chunker import JsonChunker
from foundry.ingest.markdown import MarkdownChunker
from foundry.ingest.pdf import PdfChunker
from foundry.ingest.plaintext import PlainTextChunker
from foundry.ingest.summarizer import DocumentSummarizer
from foundry.ingest.web import WebChunker

console = Console()

_DEFAULT_DB = ".foundry.db"
_EMBEDDING_MODEL = "openai/text-embedding-3-small"
_EMBEDDING_DIMS = 1536

_PDF_EXTS = {".pdf"}
_EPUB_EXTS = {".epub"}
_MD_EXTS = {".md", ".markdown"}
_JSON_EXTS = {".json"}
_TEXT_EXTS = {".txt", ".rst", ".text", ".csv", ".log"}
_GIT_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
_ALL_FILE_EXTS = _PDF_EXTS | _EPUB_EXTS | _MD_EXTS | _JSON_EXTS | _TEXT_EXTS | _AUDIO_EXTS


def ingest_cmd(
    source: Annotated[
        list[str] | None,
        typer.Option("--source", "-s", help="Source path or URL (repeatable)."),
    ] = None,
    db: Annotated[
        Path,
        typer.Option("--db", help="Path to .foundry.db (created if missing)."),
    ] = Path(_DEFAULT_DB),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be ingested without writing."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts."),
    ] = False,
    recursive: Annotated[
        bool,
        typer.Option("--recursive", help="Recurse into subdirectories (max 10 levels)."),
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob pattern to exclude (repeatable)."),
    ] = None,
) -> None:
    """Ingest one or more sources into the Foundry knowledge base."""
    sources = source or []
    excludes = exclude or []

    if not sources:
        console.print("[red]Error:[/] No --source specified. Use --source PATH_OR_URL.")
        raise typer.Exit(1)

    all_sources = _expand_sources(sources, recursive=recursive, exclude=excludes)

    if not all_sources:
        console.print("[yellow]No sources found to ingest.[/]")
        raise typer.Exit(0)

    conn = _open_db(db)
    repo = Repository(conn)
    config = EmbeddingConfig(model=_EMBEDDING_MODEL, dimensions=_EMBEDDING_DIMS)
    slug = model_to_slug(config.model)
    vec_table = ensure_vec_table(conn, slug, config.dimensions)

    try:
        for src in all_sources:
            _process_source(src, repo, vec_table, config, dry_run=dry_run, yes=yes)
    finally:
        conn.close()


# ------------------------------------------------------------------
# Per-source pipeline
# ------------------------------------------------------------------


def _process_source(
    source: str,
    repo: Repository,
    vec_table: str,
    config: EmbeddingConfig,
    dry_run: bool,
    yes: bool,
) -> None:
    """Chunk, deduplicate, embed, and summarise a single source."""
    console.print(f"\n[bold]→ {source}[/]")

    source_type = _detect_type(source)
    if source_type == "unknown":
        ext = Path(source).suffix
        console.print(f"  [red]✗ Unsupported file type:[/] {ext!r} — skipping")
        return

    # ---- Deduplication ----
    content_hash = _compute_hash(source)
    existing = repo.get_source_by_path(source)
    if existing:
        if existing.content_hash == content_hash:
            n = repo.count_chunks_by_source(existing.id)
            if n > 0:
                console.print(f"  [dim]↷ Unchanged — {n} chunks already stored[/]")
                return
            # Same hash but 0 chunks: previous run was interrupted → recover
            console.print("  [yellow]↻ Recovering partial ingest (0 chunks stored)[/]")
        else:
            console.print("  [yellow]↻ Re-ingesting (content changed)[/]")
        repo.delete_source(existing.id)

    # ---- Chunk ----
    source_id = str(uuid.uuid4())
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as prog:
        prog.add_task(f"Chunking ({source_type})…", total=None)
        try:
            chunks = _run_chunker(source_type, source_id, source, yes=yes)
        except (ValueError, RuntimeError) as exc:
            console.print(f"  [red]✗ Error:[/] {exc}")
            return

    if not chunks:
        console.print("  [yellow]✗ No chunks produced (empty source)[/]")
        return

    console.print(f"  [green]✓[/] {len(chunks)} chunks")

    if dry_run:
        console.print("  [dim]Dry run — nothing written to DB[/]")
        return

    # ---- Cost estimate + confirmation ----
    total_tokens = sum(BaseChunker.count_tokens(c.text) for c in chunks)
    _show_cost_estimate(len(chunks), total_tokens)

    if not yes:
        if not typer.confirm("  Proceed with embedding?", default=True):
            console.print("  [dim]Skipped.[/]")
            return

    # ---- Register source ----
    repo.add_source(
        Source(
            id=source_id,
            path=source,
            content_hash=content_hash,
            embedding_model=config.model,
        )
    )

    # ---- Embed ----
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[llm_calls]} LLM calls[/dim]"),
        transient=True,
        console=console,
    ) as prog:
        task = prog.add_task(
            "Embedding…",
            total=len(chunks),
            llm_calls=0,
        )

        def _on_chunk(idx: int) -> None:
            prog.update(task, completed=idx + 1, llm_calls=(idx + 1) * 2)

        EmbeddingWriter(repo, config).write(chunks, vec_table, on_progress=_on_chunk)
    console.print(f"  [green]✓[/] Embedded and stored ({len(chunks) * 2} LLM calls)")

    # ---- Summarise ----
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as prog:
        prog.add_task("Generating summary…", total=None)
        full_text = " ".join(c.text for c in chunks)
        DocumentSummarizer(repo).summarize(source_id, full_text)
    console.print("  [green]✓[/] Summary stored")


# ------------------------------------------------------------------
# Chunker dispatch
# ------------------------------------------------------------------


def _run_chunker(source_type: str, source_id: str, source: str, yes: bool) -> list:
    """Route to the correct chunker based on source type."""
    if source_type == "pdf":
        return PdfChunker().chunk(source_id, "", path=source)
    if source_type == "epub":
        return EpubChunker().chunk(source_id, "", path=source)
    if source_type in ("markdown", "json", "plaintext"):
        content = Path(source).read_text(encoding="utf-8", errors="replace")
        cls = {"markdown": MarkdownChunker, "json": JsonChunker, "plaintext": PlainTextChunker}[
            source_type
        ]
        return cls().chunk(source_id, content)
    if source_type == "audio":
        return AudioChunker(yes=yes).chunk(source_id, "", path=source)
    if source_type == "web":
        return WebChunker().chunk(source_id, "", path=source)
    if source_type == "git":
        return GitChunker().chunk(source_id, "", path=source)
    raise ValueError(f"Unsupported source type: {source_type!r}")


def _detect_type(source: str) -> str:
    """Infer source type from URL scheme or file extension."""
    if source.startswith(("https://", "http://")):
        from urllib.parse import urlparse

        try:
            host = urlparse(source).netloc.lower()
        except Exception:
            host = ""
        if source.endswith(".git") or any(h in host for h in _GIT_HOSTS):
            return "git"
        return "web"
    if source.startswith("git@"):
        return "git"
    p = Path(source)
    if p.is_dir():
        if (p / ".git").exists():
            return "git"
        return "directory"
    ext = p.suffix.lower()
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _PDF_EXTS:
        return "pdf"
    if ext in _EPUB_EXTS:
        return "epub"
    if ext in _MD_EXTS:
        return "markdown"
    if ext in _JSON_EXTS:
        return "json"
    if ext in _TEXT_EXTS:
        return "plaintext"
    return "unknown"


# ------------------------------------------------------------------
# Directory expansion
# ------------------------------------------------------------------


def _expand_sources(sources: list[str], recursive: bool, exclude: list[str]) -> list[str]:
    """Expand directories to individual files; leave URLs and files as-is."""
    result: list[str] = []
    for src in sources:
        if src.startswith(("https://", "http://", "git@")):
            result.append(src)
            continue
        p = Path(src)
        if p.is_dir() and not (p / ".git").exists():
            files = _scan_dir(p, recursive=recursive, exclude=exclude, depth=0)
            if not files:
                console.print(f"[yellow]No supported files found in directory:[/] {src}")
            result.extend(str(f) for f in files)
        else:
            result.append(src)
    return result


def _scan_dir(
    directory: Path,
    recursive: bool,
    exclude: list[str],
    depth: int,
    max_depth: int = 10,
) -> list[Path]:
    """Return supported files in *directory* (optionally recursive)."""
    if depth > max_depth:
        return []
    files: list[Path] = []
    try:
        entries = sorted(directory.iterdir())
    except PermissionError:
        return []
    for entry in entries:
        if any(fnmatch.fnmatch(entry.name, pat) for pat in exclude):
            continue
        if entry.is_file() and entry.suffix.lower() in _ALL_FILE_EXTS:
            files.append(entry)
        elif entry.is_dir() and recursive and depth < max_depth:
            files.extend(
                _scan_dir(entry, recursive=recursive, exclude=exclude, depth=depth + 1)
            )
    return files


# ------------------------------------------------------------------
# Content hashing (deduplication fingerprint)
# ------------------------------------------------------------------


def _compute_hash(source: str) -> str:
    """SHA-256 fingerprint for deduplication.

    Files: hash of content bytes.
    Remote URLs / git: hash of the URL string itself.
    Directories: hash of sorted (filename, size) pairs.
    """
    if source.startswith(("https://", "http://", "git@")):
        return hashlib.sha256(source.encode()).hexdigest()
    p = Path(source)
    if p.is_file():
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
        return h.hexdigest()
    if p.is_dir():
        h = hashlib.sha256()
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(f.name.encode())
                h.update(str(f.stat().st_size).encode())
        return h.hexdigest()
    return hashlib.sha256(source.encode()).hexdigest()


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the project database and run migrations."""
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    return conn


# ------------------------------------------------------------------
# Cost estimate display
# ------------------------------------------------------------------


def _show_cost_estimate(chunk_count: int, total_tokens: int) -> None:
    """Print a rough USD cost estimate to the console."""
    # text-embedding-3-small: $0.02 / 1M tokens
    embedding_cost = (total_tokens / 1_000_000) * 0.02
    # gpt-4o-mini context prefix: ~500 input + ~60 output per chunk
    prefix_cost = (chunk_count * 500 / 1_000_000) * 0.15 + (chunk_count * 60 / 1_000_000) * 0.60
    # summary: ~2 000 input + ~500 output (one call per source)
    summary_cost = (2_000 / 1_000_000) * 0.15 + (500 / 1_000_000) * 0.60
    total = embedding_cost + prefix_cost + summary_cost
    console.print(
        f"  [dim]Estimate: {chunk_count} chunks · {total_tokens:,} tokens · ~${total:.4f}[/]"
    )
