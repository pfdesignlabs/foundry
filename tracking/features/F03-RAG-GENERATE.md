# F03-RAG-GENERATE: RAG + Document Generation

## Doel
Relevante chunks ophalen via hybrid retrieval (BM25 + dense vector search), context
assembleren met LLM-based relevantiefiltering, en een gestructureerd document genereren
via LLM. HyDE query expansion verbetert retrieval-recall. Globale doc-samenvattingen
conditioneren de generation prompt (D0005, D0006, D0007, D0008).

## Work Items
- WI_0024: Retriever — hybrid BM25 + dense vector search
  - Twee kanalen: sqlite-vec (dense cosine similarity) + SQLite FTS5 (BM25)
  - Combineren via Reciprocal Rank Fusion: `score = 1/(k + rank_dense) + 1/(k + rank_bm25)`, k=60
  - Config: `retrieval.mode: hybrid | dense | bm25` (default hybrid), `retrieval.top_k` (default 10)
- WI_0024a: HyDE query expansion
  - Vóór retrieval: LLM genereert een kort hypothetisch antwoord op de query (1 paragraaf)
  - Hypothetisch antwoord geëmbed → gebruikt voor dense retrieval ipv ruwe query
  - Ruwe query blijft voor BM25 (keyword-matching werkt beter met de originele query)
  - Config: `retrieval.hyde: true/false` (default true), `retrieval.hyde_model` (default gpt-4o-mini)
- WI_0025: Context assembler — deduplicatie, ranking, relevantiefiltering, token budget
  - Na retrieval: elk chunk gescoord (0–10) op relevantie voor de query via LLM
  - Chunks met score < threshold weggegooid vóór context assembly
  - Config: `retrieval.scorer_model` (default gpt-4o-mini), `retrieval.relevance_threshold` (default 4)
- WI_0026: LLM client wrapper (OpenAI gpt-4o, swappable)
- WI_0027: Prompt templates (system + user, configureerbaar per project)
  - System prompt bevat globale context sectie met doc-samenvattingen van relevante bronnen
  - Template structuur: `"Background from sources:\n{source_summaries}\n\nRetrieved chunks:\n{chunks}"`
- WI_0028: Output writer — naar bestand met source attributie per sectie
- WI_0029: `foundry generate` CLI command

## Configuratie (foundry.yaml)
```yaml
retrieval:
  mode: hybrid                      # hybrid | dense | bm25
  top_k: 10                         # aantal chunks voor reranking
  hyde: true                        # HyDE query expansion aan/uit
  hyde_model: gpt-4o-mini           # model voor hypothetisch antwoord
  scorer_model: gpt-4o-mini         # model voor relevantie-scoring
  relevance_threshold: 4            # chunks onder deze score worden gefilterd (0-10)

generation:
  model: gpt-4o                     # hoofd-generatie model
  token_budget: 8192                # max context tokens voor chunks
```

## Afhankelijkheden
- F02-INGEST (chunks + contextual embeddings + doc-samenvattingen in database)

## Acceptatiecriteria
- [ ] `foundry generate --topic "onderwerp" --output output.md` werkt end-to-end
- [ ] Hybrid retrieval combineert FTS5 (BM25) + sqlite-vec (dense) via Reciprocal Rank Fusion
- [ ] HyDE: LLM genereert hypothetisch antwoord, dat wordt geëmbed voor dense retrieval
- [ ] Context assembler filtert chunks met relevantiescore < threshold (LLM-based scoring)
- [ ] System prompt bevat doc-samenvattingen van de relevante bronnen
- [ ] Output bevat bronattributie per sectie
- [ ] Context assembler respecteert token budget (configureerbaar, default 8k)
- [ ] LLM provider swappable via config (niet hard-coded OpenAI)
- [ ] `retrieval.mode`, `retrieval.hyde`, `retrieval.scorer_model`, `retrieval.relevance_threshold` instelbaar
