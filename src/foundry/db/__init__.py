"""Foundry database layer."""

from foundry.db.connection import Database
from foundry.db.migrations import MIGRATIONS, run_migrations
from foundry.db.schema import initialize
from foundry.db.vectors import ensure_vec_table, model_to_slug, vec_table_name

__all__ = [
    "Database",
    "initialize",
    "run_migrations",
    "MIGRATIONS",
    "ensure_vec_table",
    "model_to_slug",
    "vec_table_name",
]
