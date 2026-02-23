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
