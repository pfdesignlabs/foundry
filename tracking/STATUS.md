# Sprint SP_004 — Phase 3 — RAG + Generate (F03-RAG)

**Target:** 2026-03-14  
**Started:** 2026-02-24  
**Voortgang:** 7/7 work items done

**Doel:** Volledige RAG + generatie pipeline: hybrid retrieval (BM25 + dense, RRF), HyDE query expansion, context assembler (relevantie scoring, conflict detectie, token budget), LiteLLM client wrapper, prompt templates met <context> tags, output writer met footnote attributie, en foundry generate CLI command.

---

## ✅ WI_0024 — Retriever — hybrid BM25 + dense vector search met Reciprocal Rank Fusion

**Status:** done  
**Branch:** `wi/WI_0024-retriever`

**Evidence / Bewijs:**

- `src/foundry/rag/retriever.py`
- `tests/unit/rag/test_retriever.py`

**Uitkomst:**  
Hybrid retriever: BM25 (FTS5) + dense (sqlite-vec) via RRF (k=60). Modes: hybrid | dense | bm25. Vec table validatie bij startup (RuntimeError als geen embeddings voor model). 19 unit tests groen.

**Afhankelijkheden:** WI_0023

---

## ✅ WI_0024a — HyDE query expansion (LLM hypothetisch antwoord als query vector)

**Status:** done  
**Branch:** `wi/WI_0024-retriever`

**Evidence / Bewijs:**

- `src/foundry/rag/retriever.py`

**Uitkomst:**  
HyDE via litellm.completion() (hyde_model). Altijd embedding.model voor embed — geen apart hyde_embedding_model. Failure non-fatal: fallback naar ruwe query. Geïntegreerd in retriever.py (19 tests samen met WI_0024).

**Afhankelijkheden:** WI_0024

---

## ✅ WI_0025 — Context assembler — relevantie scoring, conflict detectie, token budget

**Status:** done  
**Branch:** `wi/WI_0025-context-assembler`

**Evidence / Bewijs:**

- `src/foundry/rag/assembler.py`
- `tests/unit/rag/test_assembler.py`

**Uitkomst:**  
Batch relevantie scoring (0-10) via litellm.completion(); failure → score 10. Conflict detectie: single LLM call → ConflictReport list; failure → leeg. Token budget: chunks gevuld tot token_budget via count_tokens(). 24 unit tests groen.

**Afhankelijkheden:** WI_0024a

---

## ✅ WI_0026 — LiteLLM client wrapper (retry, backoff, API key validatie)

**Status:** done  
**Branch:** `wi/WI_0026-llm-client`

**Evidence / Bewijs:**

- `src/foundry/rag/llm_client.py`
- `tests/unit/rag/test_llm_client.py`

**Uitkomst:**  
complete(), embed(), count_tokens(), get_context_window(), validate_api_key(). num_retries via LiteLLM ingebouwd (exponential backoff). count_tokens fallback: 4-char approx. get_context_window: litellm.get_model_info() + hardcoded tabel. 16 unit tests groen.

---

## ✅ WI_0027 — Prompt templates (system prompt, <context> tags, token budget validatie)

**Status:** done  
**Branch:** `wi/WI_0027-prompt-templates`

**Evidence / Bewijs:**

- `src/foundry/generate/templates.py`
- `tests/unit/generate/test_templates.py`

**Uitkomst:**  
build_prompt(): [brief → spec → summaries → <context>chunks</context>]. _load_brief(): lokaal bestand only; URL → ValueError (SSRF preventie). Token budget warning >85% context window (geen hard fail). Source summaries capped op max_source_summaries. 23 unit tests groen.

**Afhankelijkheden:** WI_0025, WI_0026

---

## ✅ WI_0028 — Output writer (footnote bronattributie, output path validatie, overwrite guard)

**Status:** done  
**Branch:** `wi/WI_0028-output-writer`

**Evidence / Bewijs:**

- `src/foundry/generate/writer.py`
- `tests/unit/generate/test_writer.py`

**Uitkomst:**  
add_attribution(): [^N] footnote block. validate_output_path(): relatieve traversal geblokkeerd; absolute paden toegestaan. check_overwrite(): prompt bij bestaand bestand; --yes slaat over. write_output(): atomisch via temp+rename. 22 unit tests groen.

**Afhankelijkheden:** WI_0027

---

## ✅ WI_0029 — foundry generate CLI command

**Status:** done  
**Branch:** `wi/WI_0029-generate-cli`

**Evidence / Bewijs:**

- `src/foundry/cli/generate.py`
- `src/foundry/cli/main.py`
- `tests/unit/cli/test_generate.py`

**Uitkomst:**  
foundry generate --topic TEXT --output PATH [--feature NAME] [--dry-run] [--yes]. Feature spec: auto-select bij één approved; --feature verplicht bij meerdere. Conflict warnings getoond vóór generatie. Token budget warning via build_prompt(). Footnote attributie via add_attribution(). 12 unit tests groen; 388 totaal.

**Afhankelijkheden:** WI_0028

---

_Gegenereerd door governor op 2026-02-24 14:59 UTC_
