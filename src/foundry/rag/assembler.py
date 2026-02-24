"""Context assembler: relevantie scoring, conflict detectie, token budget (WI_0025).

Pipeline:
  1. Score each chunk for relevance to the query (0-10, LLM batched).
     Chunks scoring below `relevance_threshold` are discarded.
  2. Detect conflicts among remaining chunks (single LLM call).
     Conflicts are reported — generation continues, operator decides.
  3. Apply token budget: fill context window up to `token_budget` tokens,
     ordered by relevance score (highest first).
  4. Return AssembledContext with final chunks, conflicts, and token counts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from foundry.db.models import Chunk
from foundry.rag.llm_client import complete, count_tokens
from foundry.rag.retriever import ScoredChunk


@dataclass
class AssemblerConfig:
    scorer_model: str = "openai/gpt-4o-mini"
    relevance_threshold: int = 4       # chunks below this score are filtered
    token_budget: int = 8_192          # max tokens for assembled context
    generation_model: str = "openai/gpt-4o"


@dataclass
class ConflictReport:
    source_a: str
    source_b: str
    description: str


@dataclass
class AssembledContext:
    chunks: list[Chunk] = field(default_factory=list)
    relevance_scores: dict[int, int] = field(default_factory=dict)  # rowid → score
    conflicts: list[ConflictReport] = field(default_factory=list)
    total_tokens: int = 0


def assemble(
    query: str,
    candidates: list[ScoredChunk],
    config: AssemblerConfig,
) -> AssembledContext:
    """Score, filter, detect conflicts, and apply token budget.

    Args:
        query: The original user query (used for relevance scoring).
        candidates: RRF-ranked chunks from the retriever.
        config: Assembler configuration.

    Returns:
        AssembledContext with filtered chunks ready for the prompt.
    """
    if not candidates:
        return AssembledContext()

    # Step 1: Relevance scoring
    scored = _score_chunks(query, candidates, config)

    # Step 2: Filter below threshold
    filtered = [
        (sc, score)
        for sc, score in scored
        if score >= config.relevance_threshold
    ]

    if not filtered:
        return AssembledContext()

    # Step 3: Sort by score descending (higher relevance first)
    filtered.sort(key=lambda x: x[1], reverse=True)
    chunks_ordered = [sc.chunk for sc, _ in filtered]
    score_map = {
        sc.chunk.rowid: score
        for sc, score in filtered
        if sc.chunk.rowid is not None
    }

    # Step 4: Conflict detection
    conflicts = _detect_conflicts(chunks_ordered, config)

    # Step 5: Apply token budget
    selected, total_tokens = _apply_token_budget(
        chunks_ordered, config.generation_model, config.token_budget
    )

    return AssembledContext(
        chunks=selected,
        relevance_scores=score_map,
        conflicts=conflicts,
        total_tokens=total_tokens,
    )


# ------------------------------------------------------------------
# Relevance scoring
# ------------------------------------------------------------------

_SCORE_SYSTEM = (
    "You are a relevance judge. For each numbered chunk, output a JSON array "
    "of integers (0-10) indicating how relevant the chunk is to the query. "
    "10 = highly relevant, 0 = completely irrelevant. "
    "Output ONLY a JSON array of integers, no explanations."
)


def _score_chunks(
    query: str,
    candidates: list[ScoredChunk],
    config: AssemblerConfig,
) -> list[tuple[ScoredChunk, int]]:
    """Batch-score all candidates for relevance to query. Returns [(ScoredChunk, score)]."""
    if not candidates:
        return []

    chunk_texts = "\n\n".join(
        f"[{i + 1}] {sc.chunk.text[:500]}"
        for i, sc in enumerate(candidates)
    )
    prompt = f"Query: {query}\n\nChunks:\n{chunk_texts}"

    try:
        raw = complete(
            model=config.scorer_model,
            messages=[
                {"role": "system", "content": _SCORE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            temperature=0,
        )
        scores = _parse_score_array(raw, expected_length=len(candidates))
    except Exception:
        # Scoring failure → treat all chunks as max relevance (non-fatal)
        scores = [10] * len(candidates)

    return list(zip(candidates, scores))


def _parse_score_array(raw: str, expected_length: int) -> list[int]:
    """Parse LLM response as JSON array of ints. Returns fallback on parse error."""
    try:
        start = raw.index("[")
        end = raw.rindex("]") + 1
        arr = json.loads(raw[start:end])
        if isinstance(arr, list) and len(arr) == expected_length:
            return [max(0, min(10, int(v))) for v in arr]
    except (ValueError, json.JSONDecodeError, TypeError):
        pass
    return [10] * expected_length


# ------------------------------------------------------------------
# Conflict detection
# ------------------------------------------------------------------

_CONFLICT_SYSTEM = (
    "You are a fact-checking assistant. Analyze the following chunks from different "
    "sources and identify any factual contradictions between them. "
    "Output a JSON array of conflict objects, each with keys: "
    "'source_a', 'source_b', 'description'. "
    "If no conflicts, output an empty array []. "
    "Output ONLY a JSON array, no explanations."
)


def _detect_conflicts(chunks: list[Chunk], config: AssemblerConfig) -> list[ConflictReport]:
    """Detect factual contradictions between chunks. Returns list of ConflictReport."""
    if len(chunks) < 2:
        return []

    chunk_texts = "\n\n".join(
        f"[Source: {c.source_id[:30]}, chunk {c.chunk_index}]\n{c.text[:400]}"
        for c in chunks[:20]  # cap at 20 to avoid huge prompts
    )

    try:
        raw = complete(
            model=config.scorer_model,
            messages=[
                {"role": "system", "content": _CONFLICT_SYSTEM},
                {"role": "user", "content": chunk_texts},
            ],
            max_tokens=512,
            temperature=0,
        )
        return _parse_conflicts(raw)
    except Exception:
        return []


def _parse_conflicts(raw: str) -> list[ConflictReport]:
    """Parse LLM conflict response. Returns empty list on parse error."""
    try:
        start = raw.index("[")
        end = raw.rindex("]") + 1
        arr = json.loads(raw[start:end])
        reports = []
        for item in arr:
            if isinstance(item, dict):
                reports.append(
                    ConflictReport(
                        source_a=str(item.get("source_a", "")),
                        source_b=str(item.get("source_b", "")),
                        description=str(item.get("description", "")),
                    )
                )
        return reports
    except (ValueError, json.JSONDecodeError, TypeError):
        return []


# ------------------------------------------------------------------
# Token budget
# ------------------------------------------------------------------


def _apply_token_budget(
    chunks: list[Chunk],
    model: str,
    budget: int,
) -> tuple[list[Chunk], int]:
    """Select chunks that fit within *budget* tokens. Returns (selected, total_tokens)."""
    selected: list[Chunk] = []
    total = 0
    for chunk in chunks:
        tokens = count_tokens(model, chunk.text)
        if total + tokens > budget:
            break
        selected.append(chunk)
        total += tokens
    return selected, total
