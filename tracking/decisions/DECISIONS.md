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

---

## D0010 — Multi-model Support: LiteLLM + Per-model Vec Tables

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Foundry werd initieel ontworpen met OpenAI als enige provider (gpt-4o, text-embedding-3-small).
Gebruikers willen kunnen experimenteren: zelfde bronnen ingesteren met meerdere embedding
modellen om retrieval-kwaliteit te vergelijken. Ook LLM-provider-onafhankelijkheid is
gewenst (OpenAI, Anthropic, lokale modellen via Ollama).

**Beslissing:**
1. LiteLLM als unified interface voor alle LLM calls (`litellm.completion()`) én
   embedding calls (`litellm.embedding()`). Provider/model gespecificeerd als één string:
   `openai/gpt-4o`, `anthropic/claude-sonnet-4-6`, `ollama/llama3`.
2. Per embedding model een aparte sqlite-vec virtual table:
   `vec_chunks_{model_slug}` (bijv. `vec_chunks_openai_text_embedding_3_small`).
   Meerdere vec tables kunnen naast elkaar bestaan in dezelfde database.
3. Vec tables zijn model-managed (niet migration-managed): aangemaakt on-demand door
   `Repository.ensure_vec_table(model_slug, dimensions)` bij eerste ingest met dat model.
4. HyDE embedding gebruikt altijd `embedding.model` — geen apart config veld.
   Token counting via `litellm.token_counter()` — provider-aware (geen tiktoken direct).

**Gevolg:**
Gebruikers kunnen experimenteren met meerdere embedding modellen op dezelfde corpus.
LiteLLM voegt één extra dependency toe (~5MB, lazy imports). Provider-switch vereist
nieuwe ingest — bestaande vec tables voor het oude model blijven intact.
API keys uitsluitend via environment variables, nooit in config files.

---

## D0011 — Per-project features/ Scaffold via foundry init

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
F04-FEATURE-GATES vereist een `features/` directory met door mensen goedgekeurde specs
als hard gate voor generatie. De spec vermeldde "door de gebruiker aangemaakt" maar dit
is onnodige handmatige stap die de onboarding verslechtert.

**Beslissing:**
`foundry init` maakt de volledige project scaffold aan als interactieve wizard:
`.foundry.db`, `foundry.yaml` (met wizard-keuzes), en een lege `features/` directory.
De gate in F04 blijft ongewijzigd — geen goedgekeurde spec = geen generatie.
De directory wordt aangemaakt door init, gevuld door de gebruiker.

**Gevolg:**
Lagere drempel voor nieuwe projecten. Geen apart "maak features/ aan" instructie nodig
in documentatie. De wizard begeleidt de gebruiker bij de initiële configuratie.

---

## D0012 — Ingest Recovery: Fresh Restart bij Onderbreking

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
Ingest kan onderbroken worden (crash, CTRL+C) na gedeeltelijke verwerking. Een partieel
geïngesteerde bron in de database leidt tot inconsistente retrieval: sommige chunks
aanwezig, andere niet, embeddings mogelijk incompleet.

**Beslissing:**
Bij herstart van ingest voor een bron die al (gedeeltelijk) in de database staat:
verwijder alle bestaande chunks + source_summaries voor die source_id en begin opnieuw.
Geen checkpointing, geen resume. Gecombineerd met content_hash deduplicatie zijn
ongewijzigde bronnen bij herstart snel (hash match → skip, geen re-ingest).

**Gevolg:**
Eenvoudige, correcte staat gegarandeerd. Kleine penalty bij herstart van grote bronnen.
Geen implementatiecomplexiteit voor checkpointing. Trade-off expliciet geaccepteerd.

---

## D0013 — sqlite-vec Rowid als Primaire Vec Lookup Key

**Datum:** 2026-02-23
**Status:** Accepted

**Context:**
sqlite-vec virtual tables gebruiken SQLite's integer rowid als lookup key. De `chunks`
tabel had UUID als PK in het initiële ontwerp. Dit creëert een impedance mismatch:
vec results retourneren een integer rowid, maar chunk lookups verwachtten een UUID.
Dit leidt tot stille bugs als de repository `WHERE id = ?` (UUID) gebruikt i.p.v.
`WHERE rowid = ?` (integer).

**Beslissing:**
`chunks` tabel gebruikt SQLite's impliciete integer rowid als primaire lookup key voor
alle vec- en FTS5-operaties. De `id` UUID kolom wordt verwijderd uit chunks — niet nodig
omdat chunks altijd via hun source worden geïdentificeerd (source_id + chunk_index).
`sources` tabel behoudt UUID als PK (extern-facing identifier).
Repository laag gebruikt altijd `WHERE c.rowid = vec_result.rowid` voor vec lookups.

**Gevolg:**
Geen impedance mismatch. Vec en FTS5 lookups zijn native integer rowid operaties.
Chunks zijn intern geïdentificeerd via (source_id, chunk_index) — geen UUID nodig.

---

## D0014 — Dual-Beneficiary Model: Operator vs. Klant

**Datum:** 2026-02-24
**Status:** Accepted

**Context:**
Foundry werd ontworpen als kennistool voor de operator (de gebruiker van Foundry zelf).
Bij gebruik voor klantprojecten (bijv. custom hardware, firmware documentatie) zijn er
echter twee begunstigden: de operator die het project beheert én de klant die de output
ontvangt. Feature specs beschrijven projecttaken (PCB layout, firmware architectuur,
assembly-procedure) — niet alleen kennisvraagtukken. Sommige gegenereerde outputs zijn
intern, sommige gaan naar de klant.

**Beslissing:**
Foundry bedient expliciet twee lagen:
1. **Operator-laag (intern):** ingest, feature specs aanmaken, tracken via `tracking/`,
   audittrail, sprint management. Niet zichtbaar voor de klant.
2. **Klant-laag (extern):** `foundry build` assembleert goedgekeurde feature-outputs
   in volgorde gedefinieerd in `delivery:` sectie van `foundry.yaml`. Output is één
   geconsolideerd `.md` document als klant-deliverable.

Feature specs zijn de eenheid van documentatie per projecttaak. De `delivery:` config
bepaalt welke specs in de klantlevering gaan (en in welke volgorde). Sommige intern
gegenereerde content (bijv. beslissingenlog) kan via `delivery.sections` in de
klantlevering opgenomen worden — dit is een per-project keuze.

`foundry init` maakt `tracking/` aan met templates voor operator-gebruik:
`sources.md` (te ingesteren bronnen), `work-items.md` (projecttaken), `build-plan.md`
(companion bij de `delivery:` config).

**Gevolg:**
Duidelijke scheiding tussen interne workflow en klantoutput. `foundry build` is de
samenstellende stap die de klantlevering produceert. Feature specs kunnen zowel intern
als extern zijn — de `delivery:` config bepaalt dit. Geen aparte "klantmodus" nodig;
de architectuur ondersteunt beide gebruikspatronen via dezelfde primitieven.

---

## D0015 — Project Governance via foundry governance Built-in

**Datum:** 2026-02-24
**Status:** Accepted

**Context:**
Foundry scaffoldt governance-machinerie in nieuwe projecten (git init, .forge/, hooks).
Het alternatief was governor.py kopiëren naar elk project. Dit leidt tot duplicatie:
bugs in governor.py moeten in elk project apart gerepareerd worden, en projecten lopen
uit de pas met de Foundry-versie die hen aanstuurde.

**Beslissing:**
Geen governor.py kopie per project. De `pre-bash.sh` hook in scaffolded projecten roept
`foundry governance bash-intercept` aan — een built-in Foundry CLI subcommand.
Hook is fail-open: `command -v foundry >/dev/null 2>&1 && exec foundry governance bash-intercept; exit 0`.
Als Foundry niet in PATH: hook doet niets (project werkt ook zonder Foundry).
`foundry governance` vereist alleen `.forge/contracts/` en `.forge/slice.yaml` — geen DB dependency.

**Gevolg:**
Governance code altijd actueel — projects gebruiken de geïnstalleerde Foundry versie.
Projecten die Foundry niet geïnstalleerd hebben: geen governance maar ook geen crash.
`.forge/` bevat: contracts/ + slice.yaml + hooks/ (NIET governor.py).

---

## D0016 — Project Context als Permanent System Prompt Context

**Datum:** 2026-02-24
**Status:** Accepted

**Context:**
`tracking/project-context.md` (gegenereerd door `foundry init` wizard) bevat project charter:
klantbehoeftes, succesfactoren, operator doelen, omgeving, capabilities, kennistekorten.
Dit document moet altijd beschikbaar zijn bij generatie — niet als reguliere bron (chunked),
maar als permanente context die elke generate-aanroep conditioneert.

**Beslissing:**
`project.brief` in foundry.yaml wijst naar `tracking/project-context.md` als lokaal bestandspad.
Foundry laadt dit bestand verbatim als eerste blok in de system prompt bij elke generate-aanroep.
Geen URL-ondersteuning voor `project.brief` (SSRF preventie). Token guard: als brief >
`project.brief_max_tokens` (default 3000) tokens: WARN + truncate.
Tracking/sources.md is bewust niet machine-parsed — tracking is human-only.

**Gevolg:**
LLM heeft altijd project context bij generatie. Operator houdt één bestand bij
(project-context.md) dat zowel planningsdocument als system prompt brief is.

---

## D0017 — Knowledge-First Workflow

**Datum:** 2026-02-24
**Status:** Accepted

**Context:**
De initiële workflow beschreef: features schrijven → ingest → generate. Dit klopt niet.
Features die blind geschreven worden (zonder kennisbank) missen contextuele precisie:
de operator weet niet wat er beschikbaar is in de bronnen, wat ontbreekt, of welke
capabilities echt haalbaar zijn gegeven de ingested kennis.

**Beslissing:**
De juiste volgorde is knowledge-first:
1. `foundry init` → project charter wizard → kennistekorten-checklist (tracking/sources.md)
2. `foundry ingest` → kennisbank opbouwen op basis van geïdentificeerde kennistekorten
3. `foundry plan` (optioneel) → LLM-assisted draft van features op basis van kennisbank
4. Feature specs schrijven (geïnformeerd door kennisbank)
5. `foundry features approve` → gate
6. `foundry generate` → review per feature
7. `foundry build` → klantlevering

**Gevolg:**
Features zijn altijd geïnformeerd door werkelijke beschikbare kennis. De init wizard
genereert een kennistekorten-checklist als startpunt voor ingest.

---

## D0018 — Hardware Lifecycle Fasen als First-class Concept

**Datum:** 2026-02-24
**Status:** Accepted

**Context:**
Hardware product development kent vaste validatiepoorten: POC → EVT-1 → EVT-x → DVT-1
→ DVT-x → PVT → MP. PF Design Labs werkt met deze fasen. Sprints in Foundry-projecten
moeten gekoppeld kunnen worden aan deze fasen voor traceerbaarheid.

**Beslissing:**
Optioneel `phase` veld op sprint-niveau in slice.yaml. Geldige waarden:
POC | EVT-1 | EVT-2 | DVT-1 | DVT-2 | PVT | MP | intern.
`foundry sprint create` wizard vraagt naar projectfase. `foundry status` toont fase-history.
Fase is optioneel — projecten zonder hardware lifecycle laten `phase` weg.

**Gevolg:**
Hardware product development lifecycle is traceerbaar per sprint. Geen verplicht onderdeel —
intern projecten en software-only projecten negeren het `phase` veld.

---

## D0019 — foundry plan als LLM-assisted Discovery Tool (F07)

**Datum:** 2026-02-24
**Status:** Accepted

**Context:**
Na initiële ingest is er een kloof tussen de kennisbank en de feature specs.
De operator moet handmatig bepalen welke capabilities features worden en welke WIs
logisch zijn. Dit kost tijd en riskeert dat capabilities over het hoofd worden gezien.

**Beslissing:**
`foundry plan` als apart CLI subcommand (F07-PLANNING). Leest project-context.md +
source_summaries uit DB. LLM analyseert capabilities → features → WIs en schrijft:
- Draft features/*.md (met disclaimer header, NOOIT ## Approved)
- Aanvulling tracking/work-items.md
- Kennistekorten-lijst die nog open staan

Menselijke review verplicht. `foundry features approve` gate blijft ongewijzigd.
Bestaande features/*.md nooit overschreven.

**Gevolg:**
Discovery → feature-writing stap versneld zonder menselijke controle te verliezen.
Prompt injection risico gemitigeerd via disclaimer header + verplichte menselijke review.
