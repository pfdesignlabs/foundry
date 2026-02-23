# F02-INGEST: Ingest Pipeline

## Doel
Bronmateriaal inlezen, in chunks opsplitsen, contextually embedden en opslaan in de
project database. Elke chunk krijgt een LLM-gegenereerde context-prefix vóór embedding
voor betere retrieval-precisie (D0004). Per bron wordt een globale samenvatting
opgeslagen voor gebruik in de generation prompt (D0008).

Ondersteunde formaten: Markdown, PDF, generiek JSON, EPUB, plain text, git (commits + diffs).

## Work Items
- WI_0015: Chunker base class + chunk model
  - Chunk velden: text, source_ref, chunk_index, metadata, context_prefix, chunk_size, overlap
- WI_0016: Markdown chunker (heading-aware splits)
  - Default: heading-aware (geen vaste size), overlap = vorige heading als context
- WI_0017: PDF chunker (pypdf, pagina-gebaseerd)
  - Default: 400 tokens / 20% overlap
- WI_0018: EPUB chunker (ebooklib, hoofdstuk-gebaseerd)
  - Default: hoofdstuk-gebaseerd, max 800 tokens per chunk
- WI_0019: JSON chunker (generiek — array of objects, of flat key-value)
  - Default: object-gebaseerd, max 300 tokens per chunk
- WI_0020: Plain text chunker (vaste window + overlap)
  - Default: 512 tokens / 10% overlap
- WI_0021: Git chunker (commits + diffs als chunks)
  - Default: per commit, max 600 tokens (diff afgekapt)
- WI_0022: Embedding writer (OpenAI text-embedding-3-small → sqlite-vec)
  - Contextual embedding: LLM (gpt-4o-mini, batchgewijs) genereert context-prefix per chunk
  - Wat geëmbed wordt: `f"{context_prefix}\n\n{chunk_text}"`
  - Chunk-tekst zelf ongewijzigd opgeslagen in chunks tabel
  - Config: `embedding.context_model` (default gpt-4o-mini)
- WI_0022a: Document-samenvatting bij ingest
  - Per ingesteerd document: LLM genereert samenvatting (max 500 tokens)
  - Opgeslagen in `source_summaries` tabel (F01-DB WI_0012b)
  - Config: `ingest.summary_model` (default gpt-4o-mini), `ingest.summary_max_tokens` (default 500)
- WI_0023: `foundry ingest` CLI command

## Configuratie (foundry.yaml)
```yaml
ingest:
  summary_model: gpt-4o-mini        # model voor doc-samenvattingen
  summary_max_tokens: 500           # max tokens per samenvatting

embedding:
  model: text-embedding-3-small     # embedding model
  context_model: gpt-4o-mini        # model voor context-prefix generatie

chunkers:
  plain_text:
    chunk_size: 512                 # tokens
    overlap: 0.10                   # fractie overlap
  pdf:
    chunk_size: 400
    overlap: 0.20
  epub:
    chunk_size: 800
    overlap: 0.10
  json:
    chunk_size: 300
    overlap: 0.0
  git:
    chunk_size: 600
    overlap: 0.0
  markdown:
    strategy: heading_aware         # alternatief: fixed_window
```

## Afhankelijkheden
- F01-DB (database laag aanwezig, inclusief FTS5 en source_summaries tabel)

## Acceptatiecriteria
- [ ] Alle 7 chunkers produceren Chunk objecten met: text, source_ref, chunk_index, metadata, context_prefix
- [ ] `foundry ingest --source /path/to/file.pdf` slaat chunks + embeddings op
- [ ] Elke chunk heeft een `context_prefix` — niet leeg na ingest
- [ ] `foundry ingest` slaat per bron een samenvatting op in source_summaries
- [ ] `chunk_size` en `overlap` instelbaar via foundry.yaml, defaults per chunker-type
- [ ] Idempotent: twee keer ingesteren van dezelfde bron = geen duplicaten
- [ ] Git chunker verwerkt commit log van een lokale repo
