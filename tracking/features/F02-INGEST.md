# F02-INGEST: Ingest Pipeline

## Doel
Bronmateriaal inlezen, in chunks opsplitsen, embedden en opslaan in de project database.
Ondersteunde formaten: Markdown, PDF, generiek JSON, EPUB, plain text, git (commits + diffs).

## Work Items
- WI_0015: Chunker base class + chunk model
- WI_0016: Markdown chunker (heading-aware splits)
- WI_0017: PDF chunker (pypdf, pagina-gebaseerd)
- WI_0018: EPUB chunker (ebooklib, hoofdstuk-gebaseerd)
- WI_0019: JSON chunker (generiek — array of objects, of flat key-value)
- WI_0020: Plain text chunker (vaste window + overlap)
- WI_0021: Git chunker (commits + diffs als chunks)
- WI_0022: Embedding writer (OpenAI text-embedding-3-small → sqlite-vec)
- WI_0023: `foundry ingest` CLI command

## Afhankelijkheden
- F01-DB (database laag aanwezig)

## Acceptatiecriteria
- [ ] Alle 6 chunkers produceren Chunk objecten met: text, source_ref, chunk_index, metadata
- [ ] `foundry ingest --source /path/to/file.pdf` slaat chunks + embeddings op
- [ ] Idempotent: twee keer ingesteren van dezelfde bron = geen duplicaten
- [ ] Git chunker verwerkt commit log van een lokale repo
