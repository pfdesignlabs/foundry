# F03-RAG-GENERATE: RAG + Document Generation

## Doel
Relevante chunks ophalen via vector similarity search, context assembleren,
en een gestructureerd Markdown document genereren via LLM.

## Work Items
- WI_0024: Retriever — query embedding + similarity search via sqlite-vec
- WI_0025: Context assembler — deduplicatie, ranking, token budget
- WI_0026: LLM client wrapper (OpenAI gpt-4o, swappable)
- WI_0027: Prompt templates (system + user, configureerbaar per project)
- WI_0028: Output writer — Markdown naar bestand met source attributie
- WI_0029: `foundry generate` CLI command

## Afhankelijkheden
- F02-INGEST (chunks + embeddings aanwezig in database)

## Acceptatiecriteria
- [ ] `foundry generate --topic "onderwerp" --output output.md` werkt end-to-end
- [ ] Output bevat bronattributie per sectie
- [ ] Context assembler respecteert token budget (configureerbaar, default 8k)
- [ ] LLM provider is swappable via config (niet hard-coded OpenAI)
