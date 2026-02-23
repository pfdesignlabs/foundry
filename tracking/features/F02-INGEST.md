# F02-INGEST: Ingest Pipeline

## Doel
Bronmateriaal inlezen, in chunks opsplitsen, contextually embedden en opslaan in de
project database. Elke chunk krijgt een LLM-gegenereerde context-prefix vóór embedding
voor betere retrieval-precisie (D0004). Per bron wordt een globale samenvatting
opgeslagen voor gebruik in de generation prompt (D0008).

Ondersteunde formaten: Markdown, PDF, generiek JSON, EPUB, plain text, git (commits + diffs).

## Work Items
- WI_0015: Chunker base class + chunk model
  - Chunk velden: text, source_id (UUID FK → sources.id), chunk_index, metadata (JSON),
    context_prefix, chunk_size, overlap
- WI_0016: Markdown chunker (heading-aware splits)
  - Default: heading-aware splits op H1/H2/H3 grenzen
  - Fallback bij geen headings: vaste window 512 tokens / 10% overlap (zelfde als plain text)
- WI_0017: PDF chunker (pypdf, pagina-gebaseerd)
  - Default: 400 tokens / 20% overlap
- WI_0018: EPUB chunker (beautifulsoup4 + html2text, hoofdstuk-gebaseerd)
  - EPUB is een ZIP van HTML bestanden — uitpakken met stdlib `zipfile`, parsen met bs4
  - Licentie: beautifulsoup4 (MIT) + html2text (GPL-3.0) — ebooklib (AGPL-3.0) niet gebruikt
  - Default: hoofdstuk-gebaseerd, max 800 tokens per chunk
- WI_0019: JSON chunker (generiek — array of objects, of flat key-value)
  - Default: object-gebaseerd, max 300 tokens per chunk
- WI_0020: Plain text chunker (vaste window + overlap)
  - Default: 512 tokens / 10% overlap
- WI_0021: Git chunker (commits + diffs als chunks)
  - Default: per commit — commit message + volledige diff (afgekapt op chunk_size tokens)
  - Lokale repo: absoluut pad, gevalideerd als bestaande directory
  - GitHub URL (https://): clone naar temp dir (`tempfile.mkdtemp(mode=0o700)`),
    ingesteer, cleanup via `try/finally` (ook bij exception) + `atexit.register()`
  - URL validatie vóór clone: alleen `https://`, `http://`, `git@` schema's toegestaan
    — geen `shell=True`, altijd `subprocess.run(["git", "clone", url, tmpdir], shell=False)`
  - Authenticatie publieke repos: direct
  - Authenticatie private repos (HTTPS): `GIT_TOKEN` env var →
    `https://{token}@github.com/...` — token nooit gelogd of in error output
  - Authenticatie SSH (`git@...`): systeem SSH keys via git natively
- WI_0022: Embedding writer (LiteLLM → sqlite-vec)
  - Interface: `litellm.embedding()` — provider/model via config
  - Contextual embedding (D0004): `litellm.completion()` genereert context-prefix per chunk
    (batchgewijs, goedkoop model)
  - Wat geëmbed wordt: `f"{context_prefix}\n\n{chunk_text}"`
  - Chunk-tekst zelf ongewijzigd opgeslagen in chunks tabel
  - Config: `embedding.context_model` (default `openai/gpt-4o-mini`)
  - Waarschuwing bij duur context_model: als het model geen `-mini` of lokaal model is,
    toont de cost estimate een expliciete waarschuwing
  - Geen API key aanwezig → hard fail met exacte instructie welke env var te zetten
- WI_0022a: Document-samenvatting bij ingest (D0008)
  - Per ingesteerd document: `litellm.completion()` genereert samenvatting (max 500 tokens)
  - Opgeslagen in `source_summaries` tabel (F01-DB WI_0012c)
  - Config: `ingest.summary_model` (default `openai/gpt-4o-mini`),
    `ingest.summary_max_tokens` (default 500)
- WI_0023: `foundry ingest` CLI command
  - `--source PATH`: bestand of directory (verplicht, herhaalbaar: `--source a.pdf --source b.pdf`)
  - **Pad validatie (security):** pad genormaliseerd en gecontroleerd — geen path traversal
    (`../../etc/passwd`). Paden buiten de opgegeven locatie → hard fail.
  - **Directory ingest:** `--source docs/` verwerkt alle bestanden direct in die directory
    (niet recursief). Herkende extensies: `.pdf`, `.md`, `.epub`, `.txt`, `.json`.
    Onbekende extensies: skip met melding (`Skipping: diagram.dxf (unsupported format)`).
    `--exclude .json` om extensies uit te sluiten.
  - `--dry-run`: toont chunk verdeling + LLM cost estimate zonder API calls
  - `--yes`: slaat cost estimate bevestigingsprompt over (voor CI/scripts)
  - Cost estimate output vóór LLM calls:
    ```
    Ingesting: datasheet.pdf
      Chunks: 247
      LLM calls: ~247 (context prefixes) + 1 (summary)  [openai/gpt-4o-mini]
      Estimated input tokens: ~74.100
      ⚠ Warning: context_model 'openai/gpt-4o' is expensive. Consider 'openai/gpt-4o-mini'.
    Continue? [y/N]:
    ```

## Deduplicatie & recovery
- **Deduplicatie**: content_hash (SHA-256) + pad gecombineerd
  - Zelfde pad + zelfde hash → skip (geen heringsest)
  - Zelfde pad + gewijzigde content → verwijder alle oude chunks voor die source_id + heringsest
  - Zelfde content op ander pad → behandeld als nieuwe bron (andere source_id)
- **Recovery bij onderbreking**: bij herstart ingest voor een bron waarvan de ingest niet
  volledig was — verwijder alle bestaande chunks voor die source_id en begin opnieuw.
  Geen checkpointing. Gecombineerd met hash-check zijn ongewijzigde bronnen snel (skip).
- **API errors**: exponential backoff via LiteLLM retry (3 pogingen, max 60s),
  daarna hard fail. Ingest gaat niet door met degraded chunks.

## Configuratie (foundry.yaml)
```yaml
ingest:
  summary_model: openai/gpt-4o-mini    # provider/model formaat (D0010)
  summary_max_tokens: 500

embedding:
  model: openai/text-embedding-3-small  # provider/model formaat (D0010)
  context_model: openai/gpt-4o-mini

chunkers:
  plain_text:
    chunk_size: 512                     # tokens
    overlap: 0.10                       # fractie overlap
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
    strategy: heading_aware             # alternatief: fixed_window
```

## Afhankelijkheden
- F01-DB (database laag aanwezig, inclusief FTS5 en source_summaries tabel)

## Acceptatiecriteria
- [ ] Alle chunkers produceren Chunk objecten met: text, source_id, chunk_index,
      metadata, context_prefix
- [ ] EPUB chunker gebruikt beautifulsoup4 + html2text — geen ebooklib (AGPL)
- [ ] Markdown chunker gebruikt heading-aware splits; fallback naar fixed_window bij geen headings
- [ ] `foundry ingest --source /path/to/file.pdf` slaat chunks + embeddings op
- [ ] `foundry ingest --source docs/` verwerkt alle direct-in-directory bestanden met
      ondersteunde extensies; onbekende extensies krijgen een skip melding
- [ ] `foundry ingest --dry-run` toont chunk verdeling + cost estimate zonder API calls
- [ ] Cost estimate toont waarschuwing als `context_model` een duur model is
- [ ] Cost estimate prompt verschijnt vóór LLM calls; `--yes` slaat prompt over
- [ ] **Pad validatie:** paden buiten opgegeven locatie → hard fail (geen path traversal)
- [ ] **Git clone:** `shell=False`, URL schema whitelist, temp dir `mode=0o700`,
      cleanup via `try/finally`
- [ ] **GIT_TOKEN:** nooit gelogd, nooit in error output, alleen in git credential helper
- [ ] Deduplicatie: zelfde bron twee keer ingesteren = geen duplicaten (hash + pad check)
- [ ] Recovery: onderbroken ingest herstart schoon (geen partieel-geïngesteerde chunks)
- [ ] Git chunker verwerkt commit log van lokale repo (message + diff per chunk)
- [ ] `foundry ingest --source https://github.com/user/repo` werkt (clone → ingest → cleanup)
- [ ] Private repo via `GIT_TOKEN`; SSH via systeem SSH keys
- [ ] Geen API key → hard fail met instructie welke env var te zetten
- [ ] `yaml.safe_load()` voor alle YAML reads — nooit `yaml.load()`
