"""foundry remove — source lifecycle management (WI_0039).

Removes a source and all its associated data from the knowledge base:
  - chunks (+ FTS5 index entries)
  - embeddings (all vec tables)
  - source summary
  - source record

Usage:
  foundry remove --source datasheet-v1.pdf
  foundry remove --source datasheet-v1.pdf --yes
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from foundry.cli.errors import err_no_db, err_source_not_found, warn_stale_outputs
from foundry.db.connection import Database
from foundry.db.repository import Repository
from foundry.db.schema import initialize

console = Console()

_DEFAULT_DB = Path(".foundry.db")


def remove_cmd(
    source: Annotated[
        str,
        typer.Option("--source", "-s", help="Source path or URL to remove."),
    ],
    db: Annotated[
        Path,
        typer.Option("--db", help="Path to .foundry.db."),
    ] = _DEFAULT_DB,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt."),
    ] = False,
) -> None:
    """Remove a source and all its data from the knowledge base."""
    if not db.exists():
        console.print(err_no_db(str(db)))
        raise typer.Exit(1)

    conn = _open_db(db)
    repo = Repository(conn)

    try:
        existing = repo.get_source_by_path(source)

        if existing is None:
            console.print(err_source_not_found(source))
            raise typer.Exit(0)

        # Gather stats for confirmation prompt
        chunk_count = repo.count_chunks_by_source(existing.id)
        has_summary = repo.get_summary(existing.id) is not None
        vec_tables = _count_vec_tables(conn)

        # Show what will be removed
        console.print(f"\nRemove source: [bold]{source}[/]")
        console.print(
            f"  Chunks: {chunk_count}  |  "
            f"Vec entries: {chunk_count} (×{vec_tables} tables)  |  "
            f"Summary: {'yes' if has_summary else 'no'}"
        )

        if not yes:
            if not typer.confirm("Confirm removal?", default=False):
                console.print("[dim]Cancelled.[/]")
                raise typer.Exit(0)

        # ---- Delete in order ----
        repo.delete_embeddings_by_source(existing.id)
        repo.delete_chunks_by_source(existing.id)
        repo.delete_summary(existing.id)
        repo.delete_source(existing.id)

        console.print(f"\n[green]✓[/] Removed: {source}")
        console.print(f"  {chunk_count} chunks, {chunk_count * vec_tables} vec entries deleted")
        console.print(f"\n{warn_stale_outputs()}")

    finally:
        conn.close()


def _open_db(db_path: Path) -> sqlite3.Connection:
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    return conn


def _count_vec_tables(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'vec_%'"
    ).fetchone()
    return rows[0] if rows else 0
