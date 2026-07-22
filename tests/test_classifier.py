"""Unit tests for the hybrid classifier — regex + LLM fallback.

All LLM calls are mocked so tests run offline and deterministically.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import ClienteConfig, IntimacaoRecord
from src.services.classifier_service import FALLBACK_CATEGORY, HybridClassifier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config() -> ClienteConfig:
    return ClienteConfig.model_validate(
        {
            "client_id": "test",
            "nome_escritorio": "Test Office",
            "advogados": [
                {"nome": "Dr. A", "senha_ref": "VAULT:A"},
            ],
            "portais_ativos": ["mercado_livre"],
            "emails_destino": ["to@example.com"],
            "use_ai_classifier": True,
            "classification_rules": {
                "execução": "Execução",
                "tutela": "Tutela",
                "recurso": "Recurso",
            },
        }
    )


@pytest.fixture
def mock_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.generate.return_value = "Recurso"
    return llm


@pytest.fixture
def classifier_no_ai() -> HybridClassifier:
    return HybridClassifier(llm_client=None)


@pytest.fixture
def classifier_with_ai(mock_llm: AsyncMock, sample_config: ClienteConfig) -> HybridClassifier:
    c = HybridClassifier(llm_client=mock_llm)
    c.load_rules(sample_config)
    return c


def _record(texto: str) -> IntimacaoRecord:
    return IntimacaoRecord(
        portal="mercado_livre",
        advogado="Dr. A",
        objeto_comunicacao=texto,
    )


# ---------------------------------------------------------------------------
# Regex matching
# ---------------------------------------------------------------------------

class TestRegexMatching:
    async def test_keyword_execucao(self, classifier_with_ai: HybridClassifier) -> None:
        cat, conf = await classifier_with_ai.classify(_record("Execução de sentença"))
        assert cat == "Execução"
        assert conf == 1.0

    async def test_keyword_case_insensitive(self, classifier_with_ai: HybridClassifier) -> None:
        cat, conf = await classifier_with_ai.classify(_record("RECURSO ESPECIAL"))
        assert cat == "Recurso"
        assert conf == 1.0

    async def test_keyword_middle_of_text(self, classifier_with_ai: HybridClassifier) -> None:
        cat, conf = await classifier_with_ai.classify(
            _record("Fica intimada a parte para manifestar sobre a tutela urgente")
        )
        assert cat == "Tutela"
        assert conf == 1.0

    async def test_first_match_wins(self, classifier_with_ai: HybridClassifier) -> None:
        # "execução" appears before "tutela" in the rules dict — but dicts
        # are insertion-ordered in Python 3.7+. Let's test that both keywords
        # in text returns the first rule matched.
        cat, conf = await classifier_with_ai.classify(
            _record("execução e tutela")
        )
        # "execução" comes first in sample_config rules
        assert cat == "Execução"
        assert conf == 1.0


# ---------------------------------------------------------------------------
# No match — regex fallback
# ---------------------------------------------------------------------------

class TestNoRegexMatch:
    async def test_empty_text_triggers_llm(self, classifier_with_ai: HybridClassifier) -> None:
        cat, conf = await classifier_with_ai.classify(_record(""))
        # LLM (mocked) returns "Recurso" for empty/unknown text
        assert cat == "Recurso"
        assert conf == 0.8

    async def test_no_keywords_triggers_llm(self, classifier_with_ai: HybridClassifier) -> None:
        cat, conf = await classifier_with_ai.classify(
            _record("Texto sem nenhuma keyword conhecida")
        )
        # LLM (mocked) returns "Recurso" when regex does not match
        assert cat == "Recurso"
        assert conf == 0.8


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

class TestLLMFallback:
    async def test_llm_called_when_regex_fails(
        self, classifier_with_ai: HybridClassifier, mock_llm: AsyncMock
    ) -> None:
        cat, conf = await classifier_with_ai.classify(
            _record("texto sem keywords")
        )
        mock_llm.generate.assert_called_once()
        assert cat == "Recurso"  # mock returns "Recurso"
        assert conf == 0.8  # ai_fallback_threshold from config

    async def test_llm_not_called_when_regex_matches(
        self, classifier_with_ai: HybridClassifier, mock_llm: AsyncMock
    ) -> None:
        await classifier_with_ai.classify(_record("Execução"))
        mock_llm.generate.assert_not_called()

    async def test_llm_unknown_category_falls_back(
        self, classifier_with_ai: HybridClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate.return_value = "CategoriaInvalida"
        cat, conf = await classifier_with_ai.classify(
            _record("texto sem keywords")
        )
        assert cat == FALLBACK_CATEGORY
        assert conf == 0.0

    async def test_llm_exception_falls_back(
        self, classifier_with_ai: HybridClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate.side_effect = RuntimeError("API down")
        cat, conf = await classifier_with_ai.classify(
            _record("texto sem keywords")
        )
        assert cat == FALLBACK_CATEGORY
        assert conf == 0.0


# ---------------------------------------------------------------------------
# AI disabled
# ---------------------------------------------------------------------------

class TestAIDisabled:
    async def test_ai_disabled_skips_llm(self, sample_config: ClienteConfig) -> None:
        sample_config.use_ai_classifier = False
        mock = AsyncMock()
        c = HybridClassifier(llm_client=mock)
        c.load_rules(sample_config)

        cat, conf = await c.classify(_record("texto sem keywords"))
        mock.generate.assert_not_called()
        assert cat == FALLBACK_CATEGORY
        assert conf == 0.0

    async def test_no_llm_client_skips_ai(self, sample_config: ClienteConfig) -> None:
        c = HybridClassifier(llm_client=None)
        c.load_rules(sample_config)

        cat, conf = await c.classify(_record("texto sem keywords"))
        assert cat == FALLBACK_CATEGORY
        assert conf == 0.0


# ---------------------------------------------------------------------------
# No rules loaded
# ---------------------------------------------------------------------------

class TestNoRules:
    async def test_no_rules_always_fallback(self) -> None:
        c = HybridClassifier(llm_client=None)
        # load_rules never called — empty keyword map
        cat, conf = await c.classify(_record("Execução"))
        assert cat == FALLBACK_CATEGORY
        assert conf == 0.0
