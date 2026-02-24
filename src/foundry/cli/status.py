"""foundry status command (WI_0037).

Shows project overview: database stats, knowledge base, features,
delivery readiness, and sprint info (if .forge/slice.yaml present).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from foundry.config import FoundryConfig, load_config
from foundry.db.connection import Database
from foundry.db.repository import Repository
from foundry.db.schema import initialize
from foundry.gates.parser import load_all_specs

console = Console()

_DEFAULT_DB = Path(".foundry.db")
_FEATURES_DIR = Path("features")
_FORGE_SLICE = Path(".forge") / "slice.yaml"


def status_cmd(
    db: Annotated[
        Path,
        typer.Option("--db", help="Path to .foundry.db."),
    ] = _DEFAULT_DB,
    features_dir: Annotated[
        Path,
        typer.Option("--features-dir", hidden=True, help="Override features/ path (for testing)."),
    ] = _FEATURES_DIR,
    slice_path: Annotated[
        Path,
        typer.Option("--slice", hidden=True, help="Override .forge/slice.yaml path (for testing)."),
    ] = _FORGE_SLICE,
) -> None:
    """Show project status: knowledge base, features, and delivery readiness."""
    # Load config (silently — status works even without foundry.yaml)
    try:
        cfg = load_config()
    except Exception:
        cfg = FoundryConfig()

    # ---- Panel 1: Project + Database ----
    _show_project_panel(db, cfg)

    # ---- Panel 2: Knowledge Base ----
    if db.exists():
        conn = _open_db(db)
        repo = Repository(conn)
        _show_knowledge_panel(db, conn, repo)
        conn.close()
    else:
        console.print(
            Panel(
                "[yellow]No database found.[/]\n"
                "  Run:  foundry init",
                title="[bold]Knowledge Base[/]",
                expand=False,
            )
        )

    # ---- Panel 3: Features ----
    _show_features_panel(features_dir)

    # ---- Panel 4: Delivery readiness ----
    if cfg.delivery.sections:
        conn2 = _open_db(db) if db.exists() else None
        _show_delivery_panel(cfg, slice_path)
        if conn2:
            conn2.close()

    # ---- Panel 5: Sprint (if .forge/slice.yaml present) ----
    if slice_path.exists():
        _show_sprint_panel(slice_path)


# ---------------------------------------------------------------------------
# Panel renderers
# ---------------------------------------------------------------------------


def _show_project_panel(db: Path, cfg: FoundryConfig) -> None:
    project_name = cfg.project.name or "(no config)"
    db_info = f"{db}"
    if db.exists():
        size_mb = db.stat().st_size / (1024 * 1024)
        db_info = f"{db} ({size_mb:.1f} MB)"

    lines = [
        f"Project:   [bold]{project_name}[/]",
        f"Database:  {db_info}",
    ]
    if cfg.project.brief:
        brief_path = Path(cfg.project.brief)
        brief_status = "[green]✓[/]" if brief_path.exists() else "[yellow]✗ missing[/]"
        lines.append(f"Brief:     {cfg.project.brief} {brief_status}")

    console.print(Panel("\n".join(lines), title="[bold]Project[/]", expand=False))


def _show_knowledge_panel(db: Path, conn: sqlite3.Connection, repo: Repository) -> None:
    sources = repo.list_sources()
    total_chunks = _count_total_chunks(conn)
    vec_tables = _list_vec_tables(conn)
    last_ingest = _last_ingest_date(sources)

    lines: list[str] = []
    lines.append(
        f"Sources: [bold]{len(sources)}[/]  |  "
        f"Chunks: [bold]{total_chunks:,}[/]  |  "
        f"Vec tables: [bold]{len(vec_tables)}[/]"
    )
    for vt in vec_tables:
        lines.append(f"  {vt}")
    if last_ingest:
        lines.append(f"Last ingest: [dim]{last_ingest}[/]")
    else:
        lines.append("[dim]No sources ingested yet.[/]")

    console.print(Panel("\n".join(lines), title="[bold]Knowledge Base[/]", expand=False))


def _show_features_panel(features_dir: Path) -> None:
    if not features_dir.is_dir():
        console.print(
            Panel(
                "[dim]No features/ directory.[/]\n"
                "  Create feature specs in features/<name>.md",
                title="[bold]Features[/]",
                expand=False,
            )
        )
        return

    specs = load_all_specs(features_dir)
    if not specs:
        console.print(
            Panel(
                "[dim]No feature specs found in features/.[/]",
                title="[bold]Features[/]",
                expand=False,
            )
        )
        return

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Status", style="bold", width=3)
    table.add_column("Name")
    table.add_column("Date", style="dim")

    for spec in specs:
        if spec.approved:
            table.add_row("[green]✓[/]", spec.name, spec.approved_on or "")
        else:
            table.add_row("[yellow]✗[/]", spec.name, "pending")

    approved = sum(1 for s in specs if s.approved)
    console.print(
        Panel(
            table,
            title=f"[bold]Features[/] [dim]({approved}/{len(specs)} approved)[/]",
            expand=False,
        )
    )


def _show_delivery_panel(cfg: FoundryConfig, slice_path: Path) -> None:
    slice_data = _load_slice(slice_path)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Name", style="bold")
    table.add_column("Type", style="dim")
    table.add_column("Status")

    for section in cfg.delivery.sections:
        name = section.feature or section.heading or section.path or "?"
        section_type = f"({section.type})"

        if section.type == "file":
            if section.path and Path(section.path).exists():
                size = Path(section.path).stat().st_size / (1024 * 1024)
                status = f"[green]✓ Present ({size:.1f} MB)[/]"
            else:
                status = "[yellow]✗ File missing[/]"

        elif section.type == "physical":
            if slice_data and section.tracking_wi:
                wi_status = _get_wi_status(slice_data, section.tracking_wi)
                if wi_status == "done":
                    status = "[green]✓ Delivered[/]"
                elif wi_status == "in_progress":
                    status = "[yellow]⏳ In Progress[/]"
                else:
                    status = "[dim]✗ Pending[/]"
            else:
                status = "[dim](no git scaffold)[/]"

        else:  # generated
            feature_name = section.feature or ""
            features_dir = Path("features")
            if features_dir.is_dir():
                specs = load_all_specs(features_dir)
                approved_names = {s.name for s in specs if s.approved}
                if feature_name in approved_names:
                    status = "[green]✓ Approved[/]"
                elif any(feature_name in s.name for s in specs):
                    status = "[yellow]✗ Not approved[/]"
                else:
                    status = "[dim]✗ Feature not found[/]"
            else:
                status = "[dim]✗ No features/[/]"

        table.add_row(name, section_type, status)

    console.print(
        Panel(table, title="[bold]Delivery Readiness[/]", expand=False)
    )


def _show_sprint_panel(slice_path: Path) -> None:
    data = _load_slice(slice_path)
    if not data:
        return

    s = data.get("slice", {})
    sprint_id = s.get("id", "?")
    sprint_name = s.get("name", "")
    phase = s.get("phase", "")
    target = s.get("target", "")

    wis = data.get("workitems", [])
    done = sum(1 for w in wis if w.get("status") == "done")
    total = len(wis)

    lines = [f"Sprint: [bold]{sprint_id}[/]  {sprint_name}"]
    if phase:
        lines.append(f"Phase:  {phase}")
    if target:
        lines.append(f"Target: [dim]{target}[/]")
    lines.append(f"WIs:    [bold]{done}/{total}[/] done")

    console.print(Panel("\n".join(lines), title="[bold]Sprint[/]", expand=False))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _open_db(db_path: Path) -> sqlite3.Connection:
    db = Database(db_path)
    conn = db.connect()
    initialize(conn)
    return conn


def _count_total_chunks(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    return row[0] if row else 0


def _list_vec_tables(conn: sqlite3.Connection) -> list[str]:
    """Return descriptions of existing vec tables (model name + dims)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'vec_%' ORDER BY name"
    ).fetchall()
    result: list[str] = []
    for (name,) in rows:
        # Try to count rows in the vec table
        try:
            count_row = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()  # noqa: S608
            count = count_row[0] if count_row else 0
            result.append(f"[dim]{name}[/] ({count:,} vectors)")
        except Exception:
            result.append(f"[dim]{name}[/]")
    return result


def _last_ingest_date(sources: list) -> str | None:
    """Return the most recent ingested_at date string across all sources."""
    dates = [s.ingested_at for s in sources if s.ingested_at]
    if not dates:
        return None
    return max(dates)[:16]  # trim to "YYYY-MM-DD HH:MM"


# ---------------------------------------------------------------------------
# Slice helpers
# ---------------------------------------------------------------------------


def _load_slice(slice_path: Path) -> dict | None:
    if not slice_path.exists():
        return None
    try:
        data = yaml.safe_load(slice_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _get_wi_status(slice_data: dict, wi_id: str) -> str:
    """Return WI status string from slice data, or 'pending' if not found."""
    for wi in slice_data.get("workitems", []):
        if wi.get("id") == wi_id:
            return str(wi.get("status", "pending"))
    return "pending"
