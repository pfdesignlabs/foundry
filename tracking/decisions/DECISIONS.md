# Foundry — Architecture Decision Record

Append-only log. Nooit bestaande entries verwijderen of aanpassen.

---

## D0001 — RAG over Claim Extraction

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
ForgeOS (voorganger) gebruikte een claim extractie pipeline: ruwe tekst → atomaire claims
→ normalisatie → canonical claims → generatie. Dit leidde tot: keyword-matching ipv semantisch
begrip, verlies van context bij atomisatie, 4 LLM-hops per document, en community claims als
ground truth.

**Beslissing:**
Foundry gebruikt RAG (Retrieval Augmented Generation): bronnen worden in chunks opgeslagen
met embeddings, en bij generatie worden relevante chunks opgehaald via vector similarity search.
Geen claim extractie, geen normalisatie pipeline, geen ClaimRow tabellen.

**Gevolg:**
Minder structuur maar beter contextueel begrip. Embeddings vervangen keyword matching.
De architectuur is eenvoudiger en schaalt beter met meer bronmateriaal.

---

## D0002 — sqlite-vec als Vector Store

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Vector stores zijn nodig voor semantic retrieval. Opties: Postgres+pgvector, Chroma,
Qdrant, Pinecone, sqlite-vec.

**Beslissing:**
sqlite-vec — SQLite virtual table extensie voor vector search. Per-project één `.db` bestand,
geen server nodig, draagbaar, dezelfde SQL interface als de rest van de database.

**Gevolg:**
Geen infrastructure overhead. Eén bestand per project. Wel beperkt in schaalbaarheid
(miljoenen vectors), maar acceptabel voor het beoogde gebruik (project knowledge bases).

---

## D0003 — Branch Hiërarchie wi/* → feat/* → develop → main

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Foundry heeft twee soorten branches nodig: werk items (granulaire taken) en features
(functionele eenheden die meerdere WIs bevatten). Protected branches: main en develop.

**Beslissing:**
Merge hiërarchie: `wi/WI_XXXX-slug` → `feat/slug` → `develop` → `main` (via `release/*`).
Directe commits op main of develop zijn geblokkeerd via governor.py + pre-bash.sh hook.
Branch naming violations zijn hard-blocked (exit 2).

**Gevolg:**
Volledige traceerbaarheid: elke wijziging in main is terug te herleiden tot een WI.
Iets meer overhead bij kleine wijzigingen, maar consistent en auditeerbaar.

---

## D0004 — Contextual Chunk Embedding (SitEmb)

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Chunks geëmbed in isolatie verliezen semantische context: de sectie, het document en de
omringende tekst zijn onzichtbaar voor het embedding model. Dit leidt tot chunks die
semantisch correct zijn maar retrieval-technisch zwak omdat ze hun positie in het
kennisgeheel missen. SitEmb paper (arXiv 2508.01959) toont significante retrieval-verbeteringen
door chunks te embedden "gesitueerd" in hun context.

**Beslissing:**
Vóór embedding genereert een LLM (gpt-4o-mini, batchgewijs) een korte context-prefix per chunk.
Wat geëmbed wordt: `context_prefix + "\n\n" + chunk_text`.
De ruwe chunk-tekst zelf wordt ongewijzigd opgeslagen in de chunks tabel.
Config: `embedding.context_model` in foundry.yaml (default gpt-4o-mini).

**Gevolg:**
Betere retrieval-precisie voor semantisch verwante maar lexicaal diverse queries.
Extra LLM-kosten bij ingest (gebatcheerd, goedkoop model). Chunk-opslag ongewijzigd —
alleen het embedded representatie verandert.

---

## D0005 — Hybrid BM25 + Dense Retrieval (SAGE)

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Dense vector search (cosine similarity) presteert slecht bij keyword-gerichte queries:
technische termen, productnamen, exacte strings, versienummers. SAGE paper (arXiv 2602.05975)
toont dat BM25 dense retrievers verslaat met ~30% voor dergelijke queries in agent-workflows.
SQLite heeft FTS5 (full-text search met BM25) ingebouwd — geen extra dependency nodig.

**Beslissing:**
Hybrid retrieval standaard: SQLite FTS5 (BM25) + sqlite-vec (dense), gecombineerd via
Reciprocal Rank Fusion (RRF): `score = 1/(k + rank_dense) + 1/(k + rank_bm25)` met k=60.
Configureerbaar via `retrieval.mode: hybrid | dense | bm25`.
Schema-uitbreiding: FTS5 virtual table in F01-DB naast sqlite-vec virtual table.

**Gevolg:**
Geen extra dependency. FTS5 vereist een extra virtual table in het schema (WI_0012a).
Repository CRUD uitbreiden met BM25 search (WI_0014). Significant betere retrieval voor
technisch domeinspecifieke content.

---

## D0006 — HyDE Query Expansion (Best Practices)

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Korte of ambigue queries ("hoe werkt X", "wat is Y") leveren slechte query-embeddings
omdat ze te weinig semantische informatie bevatten voor dense retrieval. Best Practices
paper (arXiv 2501.07391) toont dat Hypothetical Document Embedding (HyDE) retrieval-recall
significant verbetert door een rijkere embedding als query te gebruiken.

**Beslissing:**
HyDE: vóór dense retrieval genereert een LLM (gpt-4o-mini) een kort hypothetisch antwoord
op de query (1 paragraaf, <100 tokens). Dat antwoord wordt geëmbed en gebruikt als
dense retrieval query. De ruwe query blijft ongewijzigd voor BM25 (keyword-matching werkt
beter met exacte termen uit de originele query).
Config: `retrieval.hyde: true/false` (default true), `retrieval.hyde_model` (default gpt-4o-mini).

**Gevolg:**
Extra LLM-call per generate-run (klein, goedkoop model). Aanzienlijk betere recall voor
semantisch complexe of vaag geformuleerde queries.

---

## D0007 — LLM-based Post-Retrieval Relevance Scoring (Self-Reasoning RALM)

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Niet alle retrieved chunks zijn daadwerkelijk relevant voor de specifieke query — retrieval
haalt topicaal verwante maar inhoudelijk niet-relevante chunks op. Ruis in de context
verlaagt generatiekwaliteit. Self-Reasoning RALM paper (arXiv 2407.19813) toont dat
expliciete relevantie-evaluatie vóór context assembly de output-kwaliteit verbetert.

**Beslissing:**
Na retrieval: elk chunk gescoord (0–10) op relevantie voor de query via LLM (batched prompt).
Chunks met score < threshold worden niet doorgegeven aan de context assembler.
Config: `retrieval.scorer_model` (default gpt-4o-mini), `retrieval.relevance_threshold` (default 4).

**Gevolg:**
Extra LLM-calls per generate-run, gereduceerd via batching. Cleaner context → betere output.
Threshold is configureerbaar: hogere waarde = strikter filter, minder ruis maar ook minder recall.

---

## D0009 — Merge-Bron Discipline als Hard-Block in Governor

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
D0003 documenteert de merge-hiërarchie `wi/* → feat/* → develop → main`, maar de governor
handhaafde dit alleen op naam (branch-naming hard-block) en niet op merge-richting. Een
`feat/f00-scaffold` branch werd te vroeg in `develop` gemerged terwijl de bijbehorende
WIs (WI_0007–WI_0010) nog niet klaar waren. De hiërarchie was convention, niet enforcement.

**Beslissing:**
Governor breidt `_handle_bash_intercept` uit: bij `git merge` wordt de huidige branch
opgehaald via subprocess (`git rev-parse --abbrev-ref HEAD`) en de brondiscipline gevalideerd:
- `develop` accepteert alleen `feat/*` of `release/*` als bron — anders HARD-BLOCK
- `main` accepteert alleen `release/vX.Y.Z` als bron — anders HARD-BLOCK
- `feat/*` accepteert alleen `wi/*` als bron — anders WARN (niet hard-block)
Als subprocess faalt: graceful fallback naar warn (fail-open).

**Gevolg:**
De merge-hiërarchie is nu runtime geënforced, niet alleen gedocumenteerd. De fout waarbij
een feat-branch te vroeg werd gemerged kan niet meer stilzwijgend passeren binnen Claude Code.
Directe git-aanroepen buiten Claude Code omzeilen de governor nog steeds (bewust fail-open).

---

## D0008 — Global Document Summaries at Ingest (MiA-RAG + OmniThink)

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Chunk-level retrieval mist het globale beeld van een bron. De LLM weet bij generatie niet
welke soort bronnen er zijn, wat hun scope is, of hoe ze zich tot elkaar verhouden.
MiA-RAG paper (arXiv 2512.17220) toont betere coherentie via een "mindscape" (globale
samenvatting). OmniThink (arXiv 2501.09751) bevestigt dat globale context knowledge density
van gegenereerde documenten verbetert.

**Beslissing:**
Bij ingest genereert Foundry automatisch een samenvatting per bron (max 500 tokens,
gpt-4o-mini). Opgeslagen in `source_summaries` tabel (F01-DB). Meegestuurd in de
system prompt bij generatie als "Background context from sources".
Config: `ingest.summary_model` (default gpt-4o-mini), `ingest.summary_max_tokens` (default 500).

**Gevolg:**
Extra LLM-call per bron bij ingest (eenmalig, goedkoop model). System prompt wordt groter
bij veel bronnen — token budget voor chunks licht verlaagd. Betere coherentie en
contextualisering van de gegenereerde output.
