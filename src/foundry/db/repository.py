"""Repository pattern for all Foundry database operations (WI_0015).

Single interface for: sources, chunks, FTS5 search, vec embeddings, summaries.
Vec tables are model-managed (ensure_vec_table); repository handles read + write.
"""

from __future__ import annotations

import json
import sqlite3

from foundry.db.models import Chunk, Source


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def add_source(self, source: Source) -> None:
        self._conn.execute(
            """
            INSERT INTO sources (id, path, content_hash, embedding_model)
            VALUES (?, ?, ?, ?)
            """,
            (source.id, source.path, source.content_hash, source.embedding_model),
        )
        self._conn.commit()

    def get_source(self, source_id: str) -> Source | None:
        row = self._conn.execute(
            "SELECT id, path, content_hash, embedding_model, ingested_at FROM sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        return _row_to_source(row) if row else None

    def get_source_by_path(self, path: str) -> Source | None:
        row = self._conn.execute(
            "SELECT id, path, content_hash, embedding_model, ingested_at FROM sources WHERE path = ?",
            (path,),
        ).fetchone()
        return _row_to_source(row) if row else None

    def list_sources(self) -> list[Source]:
        rows = self._conn.execute(
            "SELECT id, path, content_hash, embedding_model, ingested_at FROM sources ORDER BY ingested_at"
        ).fetchall()
        return [_row_to_source(r) for r in rows]

    def delete_source(self, source_id: str) -> None:
        self._conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    def add_chunk(self, chunk: Chunk) -> int:
        """Insert chunk + sync FTS5 index. Returns the new rowid."""
        cur = self._conn.execute(
            """
            INSERT INTO chunks (source_id, chunk_index, text, context_prefix, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                chunk.source_id,
                chunk.chunk_index,
                chunk.text,
                chunk.context_prefix,
                chunk.metadata,
            ),
        )
        rowid = cur.lastrowid
        # Keep FTS5 in sync with explicit rowid mapping
        self._conn.execute(
            "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", (rowid, chunk.text)
        )
        self._conn.commit()
        return rowid

    def get_chunk_by_rowid(self, rowid: int) -> Chunk | None:
        row = self._conn.execute(
            """
            SELECT rowid, source_id, chunk_index, text, context_prefix, metadata, created_at
            FROM chunks WHERE rowid = ?
            """,
            (rowid,),
        ).fetchone()
        return _row_to_chunk(row) if row else None

    def count_chunks_by_source(self, source_id: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_id = ?", (source_id,)
        ).fetchone()[0]

    def delete_chunks_by_source(self, source_id: str) -> None:
        """Delete chunks + FTS entries for a source (cascade not available on FTS)."""
        rowids = [
            r[0]
            for r in self._conn.execute(
                "SELECT rowid FROM chunks WHERE source_id = ?", (source_id,)
            ).fetchall()
        ]
        if rowids:
            placeholders = ",".join("?" * len(rowids))
            self._conn.execute(
                f"DELETE FROM chunks_fts WHERE rowid IN ({placeholders})", rowids
            )
        self._conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Vec embeddings
    # ------------------------------------------------------------------

    def add_embedding(self, table: str, rowid: int, embedding: list[float]) -> None:
        """Insert an embedding into a vec table with explicit rowid = chunk rowid."""
        self._conn.execute(
            f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)",
            (rowid, json.dumps(embedding)),
        )
        self._conn.commit()

    def search_vec(
        self, table: str, embedding: list[float], limit: int = 10
    ) -> list[tuple[Chunk, float]]:
        """Nearest-neighbour search. Returns (chunk, distance) sorted by distance."""
        vec_rows = self._conn.execute(
            f"SELECT rowid, distance FROM {table} WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (json.dumps(embedding), limit),
        ).fetchall()

        results: list[tuple[Chunk, float]] = []
        for vec_row in vec_rows:
            chunk = self.get_chunk_by_rowid(vec_row["rowid"])
            if chunk is not None:
                results.append((chunk, vec_row["distance"]))
        return results

    # ------------------------------------------------------------------
    # FTS5 / BM25 search
    # ------------------------------------------------------------------

    def search_fts(self, query: str, limit: int = 10) -> list[tuple[Chunk, float]]:
        """BM25 full-text search. Returns (chunk, score) sorted best-first.

        bm25() returns negative values; lower (more negative) = better match.
        We return the raw bm25 score so callers can apply thresholds.
        """
        fts_rows = self._conn.execute(
            "SELECT rowid, bm25(chunks_fts) AS score FROM chunks_fts WHERE text MATCH ? ORDER BY score LIMIT ?",
            (query, limit),
        ).fetchall()

        results: list[tuple[Chunk, float]] = []
        for fts_row in fts_rows:
            chunk = self.get_chunk_by_rowid(fts_row["rowid"])
            if chunk is not None:
                results.append((chunk, fts_row["score"]))
        return results

    # ------------------------------------------------------------------
    # Source summaries
    # ------------------------------------------------------------------

    def add_summary(self, source_id: str, summary_text: str) -> None:
        self._conn.execute(
            """
            INSERT INTO source_summaries (source_id, summary_text)
            VALUES (?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                summary_text = excluded.summary_text,
                generated_at = datetime('now')
            """,
            (source_id, summary_text),
        )
        self._conn.commit()

    def get_summary(self, source_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT summary_text FROM source_summaries WHERE source_id = ?", (source_id,)
        ).fetchone()
        return row["summary_text"] if row else None

    def list_summaries(self, limit: int | None = None) -> list[tuple[str, str]]:
        """Return [(source_id, summary_text), ...] ordered by generated_at desc."""
        sql = "SELECT source_id, summary_text FROM source_summaries ORDER BY generated_at DESC"
        if limit is not None:
            sql += f" LIMIT {limit}"
        return [(r["source_id"], r["summary_text"]) for r in self._conn.execute(sql).fetchall()]

    def delete_summary(self, source_id: str) -> None:
        self._conn.execute(
            "DELETE FROM source_summaries WHERE source_id = ?", (source_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Vec embeddings — bulk delete by source (WI_0039)
    # ------------------------------------------------------------------

    def delete_embeddings_by_source(self, source_id: str) -> int:
        """Delete all vec embeddings for *source_id* from every vec table.

        Returns the total number of embedding rows deleted across all vec tables.
        """
        rowids = [
            r[0]
            for r in self._conn.execute(
                "SELECT rowid FROM chunks WHERE source_id = ?", (source_id,)
            ).fetchall()
        ]
        if not rowids:
            return 0

        vec_tables = [
            r[0]
            for r in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'vec_%'"
            ).fetchall()
        ]

        total_deleted = 0
        placeholders = ",".join("?" * len(rowids))
        for table in vec_tables:
            cur = self._conn.execute(
                f"DELETE FROM [{table}] WHERE rowid IN ({placeholders})",  # noqa: S608
                rowids,
            )
            total_deleted += cur.rowcount

        self._conn.commit()
        return total_deleted


# ------------------------------------------------------------------
# Row → model helpers
# ------------------------------------------------------------------

def _row_to_source(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"],
        path=row["path"],
        content_hash=row["content_hash"],
        embedding_model=row["embedding_model"],
        ingested_at=row["ingested_at"],
    )


def _row_to_chunk(row: sqlite3.Row) -> Chunk:
    return Chunk(
        rowid=row["rowid"],
        source_id=row["source_id"],
        chunk_index=row["chunk_index"],
        text=row["text"],
        context_prefix=row["context_prefix"],
        metadata=row["metadata"],
        created_at=row["created_at"],
    )
