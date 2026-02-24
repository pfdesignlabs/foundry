# Sprint SP_002 — Phase 1 — Database Layer (F01-DB)

**Target:** 2026-03-07  
**Started:** 2026-02-24  
**Voortgang:** 0/6 work items done

**Doel:** SQLite database schema opzetten met sqlite-vec extensie voor vector search. Sources + chunks tabellen, per-model vec tables (ensure_vec_table), FTS5 BM25 full-text search, source_summaries tabel, forward-only migration runner en repository pattern implementeren. Fundament voor alle ingest + retrieval.

---

## ❓ WI_0012 — Verbindingslaag + schema: sources + chunks tabellen

**Status:** pending  
**Branch:** `—`

**Beschrijving:**  
SQLite verbinding opzetten met sqlite-vec extensie. Sources tabel: id (UUID TEXT PK), path (TEXT relatief), content_hash (TEXT SHA-256), embedding_model (TEXT), ingested_at (DATETIME). Chunks tabel: rowid (INTEGER implicit PK), source_id (FK), chunk_index (INT), text (TEXT), context_prefix (TEXT), metadata (JSON), created_at (DATETIME). schema_version tabel voor migration tracking.

---

## ❓ WI_0012a — Per-model sqlite-vec virtual tables (ensure_vec_table)

**Status:** pending  
**Branch:** `—`

**Beschrijving:**  
ensure_vec_table(model_slug, dimensions) implementeren — maakt vec_chunks_{model_slug} aan als nog niet bestaat. Naam bijv. vec_chunks_openai_text_embedding_3_small. rowid = chunks.rowid (native sqlite-vec mapping). Niet migration-managed.

**Afhankelijkheden:** WI_0012

---

## ❓ WI_0012b — FTS5 virtual table voor BM25 full-text search

**Status:** pending  
**Branch:** `—`

**Beschrijving:**  
chunks_fts FTS5 virtual table aanmaken. rowid = chunks.rowid (native FTS5 content table mapping). BM25 search via MATCH operator.

**Afhankelijkheden:** WI_0012

---

## ❓ WI_0012c — source_summaries tabel

**Status:** pending  
**Branch:** `—`

**Beschrijving:**  
source_summaries tabel: source_id (FK → sources.id), summary_text (TEXT), generated_at (DATETIME). Ophaalbaar per source_id.

**Afhankelijkheden:** WI_0012

---

## ❓ WI_0013 — Migration runner (forward-only, geen rollbacks)

**Status:** pending  
**Branch:** `—`

**Beschrijving:**  
Embedded Python migration runner: MIGRATIONS = [(version, sql), ...]. schema_version tabel bijhouden. Idempotent: twee keer uitvoeren = zelfde staat. Beheert alleen statische tabellen — vec tables zijn model-managed (niet hier).

**Afhankelijkheden:** WI_0012, WI_0012a, WI_0012b, WI_0012c

---

## ❓ WI_0015 — Repository pattern: chunk CRUD + FTS5 search + vec lookup + summaries

**Status:** pending  
**Branch:** `—`

**Beschrijving:**  
Repository klasse voor alle database operaties: chunk insert/get/delete, source insert/get, FTS5 BM25 search, vec lookup (rowid mapping), source_summaries CRUD. Vec lookups via: SELECT c.* FROM chunks c WHERE c.rowid = vec_result.rowid. Retrieval geeft (chunk, score) tuples terug.

**Afhankelijkheden:** WI_0013

---

_Gegenereerd door governor op 2026-02-24 10:23 UTC_
