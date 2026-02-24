"""LiteLLM client wrapper with retry, backoff, and API key validation (WI_0026).

All LLM + embedding calls in the RAG/generate pipeline route through this module.
LiteLLM's built-in retry is used (num_retries=3, exponential backoff, max 60s).
API key presence is validated at startup before any generation begins.
"""

from __future__ import annotations

import os

import litellm

# Disable LiteLLM verbose logging unless explicitly enabled
litellm.suppress_debug_info = True
litellm.set_verbose = False  # type: ignore[assignment]


# ------------------------------------------------------------------
# Provider → env var mapping for API key validation
# ------------------------------------------------------------------

_PROVIDER_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_API_KEY",
    "cohere": "COHERE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "ollama": None,  # Local, no key required
    "ollama_chat": None,
}


def validate_api_key(model: str) -> None:
    """Check that the required API key env var is set for *model*.

    Args:
        model: LiteLLM model string in 'provider/model' format.

    Raises:
        EnvironmentError: If the required key is missing from environment.
    """
    provider = model.split("/")[0].lower() if "/" in model else "openai"
    env_var = _PROVIDER_ENV.get(provider)

    if env_var is None:
        return  # No key required (e.g. ollama)

    if not os.getenv(env_var):
        raise EnvironmentError(
            f"API key not found for provider '{provider}'. "
            f"Set the {env_var} environment variable."
        )


def complete(
    model: str,
    messages: list[dict],
    max_tokens: int = 2048,
    temperature: float = 0.0,
    num_retries: int = 3,
) -> str:
    """Call litellm.completion() with retry/backoff. Returns content string.

    Args:
        model: LiteLLM model string (provider/model format).
        messages: OpenAI-style message list.
        max_tokens: Maximum output tokens.
        temperature: Sampling temperature (0 = deterministic).
        num_retries: Number of retries on transient errors (exponential backoff).

    Returns:
        The text content of the first choice.

    Raises:
        litellm.exceptions.APIError: On persistent API failure after retries.
    """
    response = litellm.completion(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        num_retries=num_retries,
    )
    return response.choices[0].message.content or ""


def embed(model: str, text: str, num_retries: int = 3) -> list[float]:
    """Call litellm.embedding() with retry/backoff. Returns embedding vector.

    Args:
        model: LiteLLM embedding model string (provider/model format).
        text: Text to embed.
        num_retries: Number of retries on transient errors.

    Returns:
        Embedding as a list of floats.
    """
    response = litellm.embedding(
        model=model,
        input=[text],
        num_retries=num_retries,
    )
    return response.data[0]["embedding"]


def count_tokens(model: str, text: str) -> int:
    """Count tokens in *text* for *model* using LiteLLM's provider-aware counter.

    Falls back to character-based approximation (4 chars ≈ 1 token) if the model
    is not supported by litellm.token_counter().
    """
    try:
        return litellm.token_counter(model=model, text=text)
    except Exception:
        return max(1, len(text) // 4)


def get_context_window(model: str) -> int:
    """Return the context window size for *model* in tokens.

    Uses litellm.get_model_info() with a hardcoded fallback table for common models.
    Returns 8192 if the model is unknown.
    """
    try:
        info = litellm.get_model_info(model)
        return info.get("max_input_tokens") or info.get("max_tokens") or 8192
    except Exception:
        pass

    # Fallback lookup table for common models
    _FALLBACK: dict[str, int] = {
        "openai/gpt-4o": 128_000,
        "openai/gpt-4o-mini": 128_000,
        "openai/gpt-4-turbo": 128_000,
        "openai/gpt-3.5-turbo": 16_384,
        "anthropic/claude-3-5-sonnet-20241022": 200_000,
        "anthropic/claude-3-5-haiku-20241022": 200_000,
        "anthropic/claude-3-opus-20240229": 200_000,
    }
    return _FALLBACK.get(model, 8_192)
