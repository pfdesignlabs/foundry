# F01-DB: Database Layer (sqlite-vec)

## Doel
SQLite database schema opzetten met sqlite-vec extensie voor vector search.
Per-project database met chunk + embedding opslag, BM25 full-text search,
document-samenvattingen en een migration runner.

## Work Items
- WI_0012: Verbindingslaag + schema — `sources` tabel + `chunks` tabel
  - sqlite-vec extensie laden en verbinding opzetten
  - sources: id (UUID TEXT PK), path (TEXT, relatief t.o.v. project root),
    content_hash (TEXT, SHA-256), embedding_model (TEXT), ingested_at (DATETIME)
  - chunks: rowid (INTEGER, implicit PK — gebruikt door sqlite-vec), source_id (FK → sources.id),
    chunk_index (INT), text (TEXT), context_prefix (TEXT), metadata (JSON), created_at (DATETIME)
- WI_0012a: Per-model sqlite-vec virtual tables
  - Naam: `vec_chunks_{model_slug}` (bijv. `vec_chunks_openai_text_embedding_3_small`)
  - rowid in vec table = rowid van chunks tabel (native sqlite-vec mapping)
  - Niet migration-managed — aangemaakt on-demand via `ensure_vec_table(model_slug, dimensions)`
  - Repository registreert welke vec tables bestaan via sources.embedding_model kolom
- WI_0012b: FTS5 virtual table voor BM25 full-text search
  - Naam: `chunks_fts`
  - rowid = chunks.rowid (native FTS5 content table mapping)
- WI_0012c: `source_summaries` tabel
  - source_id (FK → sources.id), summary_text (TEXT), generated_at (DATETIME)
- WI_0013: Migration runner (forward-only, geen rollbacks)
  - Embedded Python: `MIGRATIONS = [(version: int, sql: str), ...]`
  - `schema_version` tabel: version (INT), applied_at (DATETIME)
  - Beheert alleen statische tabellen (sources, chunks, source_summaries, chunks_fts,
    schema_version). Vec tables zijn model-managed, niet migration-managed.
  - Idempotent: twee keer uitvoeren = zelfde staat
- WI_0015: Repository pattern voor chunk CRUD + FTS5 search + summaries
  - `ensure_vec_table(model_slug: str, dimensions: int)` — aanmaken als nog niet bestaat
  - Vec lookups: `SELECT c.* FROM chunks c WHERE c.rowid = vec_result.rowid`
  - Retrieval teruggeven als `(chunk, score)` tuples

## Schema overzicht
```
sources           id (UUID TEXT PK), path (TEXT, relatief), content_hash (TEXT),
                  embedding_model (TEXT), ingested_at (DATETIME)
chunks            rowid (INTEGER implicit PK), source_id (TEXT FK → sources.id),
                  chunk_index (INT), text (TEXT), context_prefix (TEXT),
                  metadata (TEXT/JSON), created_at (DATETIME)
source_summaries  source_id (TEXT FK → sources.id), summary_text (TEXT),
                  generated_at (DATETIME)
vec_chunks_{slug} sqlite-vec virtual table — rowid = chunks.rowid, embedding float[N]
                  (model-managed, niet migration-managed)
chunks_fts        FTS5 virtual table — rowid = chunks.rowid, text
schema_version    version (INT), applied_at (DATETIME)
```

## Vec table lifecycle
Vec tables zijn NIET migration-managed. Ze bestaan alleen als het bijbehorende
embedding model gebruikt is. Repository aanroep `ensure_vec_table()` vóór eerste
embedding write. De `sources.embedding_model` kolom registreert welke modellen
gebruikt zijn — zo is altijd te reconstrueren welke vec tables aanwezig zouden moeten zijn.

## Afhankelijkheden
- F00-SCAFFOLD (WI_0001–WI_0011 — fundament aanwezig)

## Acceptatiecriteria
- [ ] `foundry init` maakt `.foundry.db` aan in de project directory
- [ ] `sources` tabel slaat pad (relatief), content_hash en embedding_model op
- [ ] sqlite-vec extensie laadt zonder errors
- [ ] Vec lookup gebruikt `chunks.rowid`, niet een UUID veld
- [ ] `ensure_vec_table()` maakt per-model vec table aan on-demand
- [ ] Meerdere vec tables (verschillende modellen) kunnen naast elkaar bestaan
- [ ] FTS5 virtual table aanwezig, BM25 search retourneert gerankte resultaten
- [ ] source_summaries tabel aanwezig en ophaalbaar per source_id
- [ ] Migration runner draait idempotent (twee keer uitvoeren = zelfde staat)
- [ ] Vec tables worden NIET door migration runner aangemaakt
