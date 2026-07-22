"""Hybrid classifier — regex first (free), LLM second (paid).

The classification pipeline:
1. **Keyword match** — iterate the client's ``classification_rules`` dict.
   If the record text contains a keyword → category + confidence 1.0.
2. **LLM** (optional, gated by config) — ask the model.  Only the exact
   category set is accepted; any other response is discarded.
3. **Fallback** — return ``"CLASSIFICACAO_MANUAL"`` / 0.0 so the analyst
   can triage.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.interfaces.classifier import Classifier
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.models import ClienteConfig, IntimacaoRecord
    from src.services.llm_client import LLMClient

logger = get_logger(__name__)

FALLBACK_CATEGORY = "CLASSIFICACAO_MANUAL"


class HybridClassifier(Classifier):
    """Classify intimations using a two-tier strategy (regex → LLM → manual)."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client
        self._rules: dict[str, str] = {}  # keyword → category
        self._client_config: ClienteConfig | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_rules(self, client_config: ClienteConfig) -> None:
        """Ingest the client's classification rules.

        Called once per run by the orchestrator after loading the config.
        """
        self._client_config = client_config
        self._rules = {
            kw.strip().lower(): cat.strip()
            for kw, cat in client_config.classification_rules.items()
        }
        logger.info(
            "Loaded %d classification rules for client %r",
            len(self._rules),
            client_config.client_id,
        )

    # ------------------------------------------------------------------
    # Classifier interface
    # ------------------------------------------------------------------

    async def classify(self, record: IntimacaoRecord) -> tuple[str, float]:
        """Run the full classification pipeline for a single record."""
        texto = (record.objeto_comunicacao or "").strip()

        # ---- Stage 1: regex / keyword match ----------------------------
        if texto:
            lowered = texto.lower()
            for keyword, category in self._rules.items():
                if keyword in lowered:
                    logger.debug(
                        "Keyword %r matched → %r (proc: %s)",
                        keyword,
                        category,
                        record.numero_processo,
                    )
                    return category, 1.0

        # ---- Stage 2: LLM ----------------------------------------------
        if self._should_use_llm():
            result = await self._classify_via_llm(texto)
            if result is not None:
                return result

        # ---- Stage 3: fallback -----------------------------------------
        return FALLBACK_CATEGORY, 0.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _should_use_llm(self) -> bool:
        if self._llm is None:
            return False
        if self._client_config is None:
            return False
        return self._client_config.use_ai_classifier

    async def _classify_via_llm(self, texto: str) -> tuple[str, float] | None:
        """Send the text to the LLM and validate the answer.

        Returns ``None`` when the LLM is unavailable, times out, or returns
        an invalid category — the caller should fall back.
        """
        assert self._client_config is not None
        assert self._llm is not None

        categorias = sorted(set(self._rules.values()))
        if not categorias:
            return None

        prompt = _build_llm_prompt(texto, categorias)

        try:
            resposta = await asyncio.wait_for(
                self._llm.generate(prompt), timeout=15.0
            )
            resposta = resposta.strip()

            # Strict match — LLM must return exactly one of the known categories
            for cat in categorias:
                if resposta.lower() == cat.lower():
                    logger.debug("LLM classified → %r", cat)
                    return cat, self._client_config.ai_fallback_threshold

            logger.warning("LLM returned unknown category %r — falling back", resposta)

        except asyncio.TimeoutError:
            logger.error("LLM timeout after 15s")
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)

        return None


# -----------------------------------------------------------------------
# Prompt template
# -----------------------------------------------------------------------

def _build_llm_prompt(texto: str, categorias: list[str]) -> str:
    cats = "\n".join(f"- {c}" for c in categorias)
    return (
        "Classifique o texto abaixo em EXATAMENTE UMA das seguintes "
        "categorias:\n\n"
        f"{cats}\n\n"
        "Responda APENAS com o nome da categoria, sem explicações, "
        "numeração ou pontuação adicional.\n\n"
        f'Texto: """{texto}"""'
    )
