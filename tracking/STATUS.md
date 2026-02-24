# Foundry — Sprint Status

_Auto-gegenereerd. Niet handmatig bewerken._
_Bijgewerkt: 2026-02-24_

---

## Huidige sprint: SP_004 — Phase 3 — RAG + Generate (F03-RAG)

**Target:** 2026-03-14
**Started:** 2026-02-24
**Voortgang:** 7/7 work items done ✅

**Doel:** Volledige RAG + generatie pipeline: hybrid retrieval (BM25 + dense, RRF), HyDE query expansion, context assembler, LiteLLM client wrapper, prompt templates, output writer, foundry generate CLI command.

**Testtotaal:** 388 unit tests groen

| WI | Titel | Status |
|----|-------|--------|
| WI_0024 | Retriever — hybrid BM25 + dense (RRF) | ✅ done |
| WI_0024a | HyDE query expansion | ✅ done |
| WI_0025 | Context assembler | ✅ done |
| WI_0026 | LiteLLM client wrapper | ✅ done |
| WI_0027 | Prompt templates | ✅ done |
| WI_0028 | Output writer | ✅ done |
| WI_0029 | foundry generate CLI command | ✅ done |

---

## Sprint history

| Sprint | Naam | WIs | Status |
|--------|------|-----|--------|
| SP_001 | Scaffold + DEV_GOVERNANCE | 6/10 | ✅ done (deels) |
| SP_002 | Phase 1 — DB Layer (F01-DB) | 6/6 | ✅ done |
| SP_003 | Phase 2 — Ingest Pipeline (F02-INGEST) | 11/11 | ✅ done |
| SP_004 | Phase 3 — RAG + Generate (F03-RAG) | 7/7 | ✅ done |

### Volgende fase
**SP_005 — Phase 4: Feature Gates (F04-FEATURE-GATES)**
- WI_0030: Feature spec parser (^## Approved$)
- WI_0031: Approval check + gate enforcement
- WI_0032: foundry features list
- WI_0033: foundry features approve

---

## Codebase overzicht

```
src/foundry/
  cli/          ← ingest + generate commands
  db/           ← schema, connection, repository, migrations, vectors
  ingest/       ← chunkers: MD, PDF, EPUB, JSON, txt, git, web, audio
                   embedding writer, summarizer
  rag/          ← retriever (hybrid BM25+dense, RRF), HyDE, assembler, llm_client
  generate/     ← templates (prompt builder), writer (output + attribution)

tests/unit/     ← 388 tests (mirrors src/)
```
