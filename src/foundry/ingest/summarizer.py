"""Document summarizer — generate per-source summaries via LiteLLM (WI_0022a).

Called once per ingested source after all chunks are embedded.
Stores the summary in source_summaries table for use in generation prompts (D0008).
"""

from __future__ import annotations

import litellm

from foundry.db.repository import Repository

_SUMMARY_PROMPT = """\
You are a document assistant. Write a concise summary (max {max_tokens} tokens) \
of the following document that will be used as context for a retrieval-augmented \
generation system. Focus on the key topics, findings, and information present.

Document excerpt (first 8000 characters):
{document_text}

Summary:"""

_DEFAULT_MODEL = "openai/gpt-4o-mini"
_DEFAULT_MAX_TOKENS = 500


class DocumentSummarizer:
    """Generate and persist a summary for an ingested source document.

    Args:
        repo:       Open Repository instance.
        model:      LiteLLM model string for summary generation.
        max_tokens: Maximum tokens in the generated summary.
    """

    def __init__(
        self,
        repo: Repository,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._repo = repo
        self._model = model
        self._max_tokens = max_tokens

    def summarize(self, source_id: str, full_text: str) -> str:
        """Generate a summary for *source_id* and store it in the DB.

        Returns the generated summary string.
        If summary generation fails, an empty string is stored (non-fatal).
        """
        summary = self._generate(full_text)
        self._repo.add_summary(source_id, summary)
        return summary

    def _generate(self, full_text: str) -> str:
        """Call litellm.completion() to generate the summary."""
        prompt = _SUMMARY_PROMPT.format(
            max_tokens=self._max_tokens,
            document_text=full_text[:8000],
        )
        try:
            response = litellm.completion(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception:
            return ""
