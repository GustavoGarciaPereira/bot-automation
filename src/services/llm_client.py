"""Thin wrapper around LangChain for LLM-based classification.

Supports (priority order):
1. DeepSeek    — ``DEEPSEEK_API_KEY`` (or legacy ``LLM_API_KEY``)
2. OpenAI      — ``OPENAI_API_KEY`` (vanilla or compatible)

All providers use the OpenAI-compatible API via ``langchain_openai.ChatOpenAI``.
Configuration is 100% environment-driven — nothing is hardcoded.

The client is optional — if no API key is configured the orchestrator
skips AI classification and uses regex-only mode.
"""

from __future__ import annotations

import os
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Defaults (overridable via env vars)
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"
_DEFAULT_TEMPERATURE = 0.0
_DEFAULT_TIMEOUT = 30
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_MAX_TOKENS = 512


class LLMClient:
    """Async wrapper around LangChain's ``ChatOpenAI``.

    Works with DeepSeek, OpenAI, or any OpenAI-compatible API.
    Instantiate once and inject into ``HybridClassifier``.
    """

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        **kwargs: Any,
    ) -> None:
        # -- Resolve config (arg → env → default) -------------------------
        self._api_key = (
            api_key
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self._model_name = (
            model_name
            or os.getenv("DEEPSEEK_MODEL")
            or os.getenv("LLM_MODEL", _DEFAULT_MODEL)
        )
        self._base_url = (
            base_url
            or os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("LLM_BASE_URL", _DEFAULT_BASE_URL)
        )
        self._temperature = (
            temperature
            if temperature is not None
            else float(os.getenv("LLM_TEMPERATURE", str(_DEFAULT_TEMPERATURE)))
        )
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._extra_kwargs = kwargs

        if not self._api_key:
            raise ValueError(
                "Nenhuma API key configurada. Defina DEEPSEEK_API_KEY ou OPENAI_API_KEY no .env"
            )

        # Build eagerly so misconfiguration fails fast
        self._llm = self._build_llm()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(self, prompt: str) -> str:
        """Send *prompt* to the LLM and return the trimmed response text.

        Raises ``RuntimeError`` on transport / API failures so the
        ``HybridClassifier`` can fall back to ``CLASSIFICACAO_MANUAL``.
        """
        from langchain_core.messages import HumanMessage

        try:
            response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            content: str = response.content  # type: ignore[assignment]
            return content.strip()
        except Exception as exc:
            raise RuntimeError(
                f"LLM call failed (provider={self._provider_label}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> LLMClient | None:
        """Create an ``LLMClient`` from environment variables.

        Priority: ``DEEPSEEK_API_KEY`` → ``LLM_API_KEY`` → ``OPENAI_API_KEY``.
        Returns ``None`` when no API key is configured so the orchestrator
        can skip AI classification gracefully.
        """
        # 1. DeepSeek (new var name)
        if os.getenv("DEEPSEEK_API_KEY"):
            logger.info("LLM: DeepSeek (model=%s)", os.getenv("DEEPSEEK_MODEL", _DEFAULT_MODEL))
            return cls()

        # 2. DeepSeek / custom (legacy var name)
        if os.getenv("LLM_API_KEY"):
            logger.info("LLM: DeepSeek / custom provider (model=%s)", os.getenv("LLM_MODEL", _DEFAULT_MODEL))
            return cls()

        # 3. Vanilla OpenAI
        if os.getenv("OPENAI_API_KEY"):
            logger.info("LLM: OpenAI (model=%s)", os.getenv("LLM_MODEL", "gpt-4o-mini"))
            return cls(
                model_name=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                base_url=None,  # use OpenAI's default
            )

        logger.info("No LLM API key found — AI classification disabled")
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @property
    def _provider_label(self) -> str:
        if os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY"):
            return os.getenv("DEEPSEEK_BASE_URL") or os.getenv("LLM_BASE_URL", _DEFAULT_BASE_URL)
        return "openai"

    def _build_llm(self) -> Any:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "timeout": self._timeout,
            "max_retries": self._max_retries,
        }

        # DeepSeek / OpenAI / any compatible provider
        kwargs["base_url"] = self._base_url
        kwargs["api_key"] = self._api_key

        # Merge any remaining extra kwargs
        kwargs.update(
            {k: v for k, v in self._extra_kwargs.items() if k not in kwargs}
        )

        logger.debug(
            "ChatOpenAI: model=%s base_url=%s timeout=%ds retries=%d",
            self._model_name,
            kwargs.get("base_url", "(default)"),
            self._timeout,
            self._max_retries,
        )

        return ChatOpenAI(**kwargs)

