# F01-DB: Database Layer (sqlite-vec)

## Doel
SQLite database schema opzetten met sqlite-vec extensie voor vector search.
Per-project database met chunk + embedding opslag, BM25 full-text search,
document-samenvattingen en een migration runner.

## Work Items
- WI_0011: sqlite-vec installatie + verbindingslaag
- WI_0012: Schema — chunks tabel, embeddings virtual table (sqlite-vec)
- WI_0012a: FTS5 virtual table voor BM25 full-text search (naast sqlite-vec)
- WI_0012b: `source_summaries` tabel — source_id, summary_text, generated_at
- WI_0013: Migration runner (forward-only, geen rollbacks)
- WI_0014: Repository pattern voor chunk CRUD + FTS5 search + summaries

## Afhankelijkheden
- F00-SCAFFOLD (WI_0001–WI_0006 — fundament aanwezig)

## Acceptatiecriteria
- [ ] `foundry init --project /path/to/project` maakt een `.foundry.db` aan
- [ ] sqlite-vec extensie laadt zonder errors
- [ ] Chunks kunnen worden opgeslagen en opgehaald via repository
- [ ] Vector similarity search geeft resultaten terug op dummy embeddings
- [ ] FTS5 virtual table aanwezig, BM25 search retourneert gerankte resultaten
- [ ] source_summaries tabel aanwezig en ophaalbaar per source_id
- [ ] Migration runner draait idempotent (twee keer uitvoeren = zelfde staat)
