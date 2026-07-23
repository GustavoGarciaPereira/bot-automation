"""Unit tests for the Reclame Aqui plugin.

Uses cloudscraper + BeautifulSoup (no Selenium needed).
All HTTP calls are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugins.reclame_aqui.models import Complaint, CompanyReport
from src.plugins.reclame_aqui.scraper import (
    ReclameAquiScraper,
    _clear_config_cache,
    slugify,
)

# ---------------------------------------------------------------------------
# Sample HTML snippets
# ---------------------------------------------------------------------------

SAMPLE_LIST_HTML = """
<div class="complaint-card">
  <h2 class="complaint-card__title">
    <a href="/reclamacao/123">Produto não entregue</a>
  </h2>
  <span class="complaint-card__date">15/07/2026</span>
  <span class="complaint-card__status">Respondida</span>
  <p class="complaint-card__text">Pedido não foi entregue no prazo.</p>
</div>
<div class="complaint-card">
  <h2 class="complaint-card__title">
    <a href="/reclamacao/456">Cobrança indevida</a>
  </h2>
  <span class="complaint-card__date">10/07/2026</span>
  <span class="complaint-card__status">Não respondida</span>
  <p class="complaint-card__text">Fui cobrado sem motivo.</p>
</div>
<div class="complaint-card">
  <h2 class="complaint-card__title">
    <a href="/reclamacao/789">Atendimento ruim</a>
  </h2>
  <span class="complaint-card__date">05/07/2026</span>
  <span class="complaint-card__status">Em tratamento</span>
  <p class="complaint-card__text">Demoraram muito para responder.</p>
</div>
"""

SAMPLE_EMPTY_HTML = """
<html><body><div class="no-results">Nenhuma reclamação encontrada</div></body></html>
"""

SAMPLE_DETAIL_HTML = """
<html>
<h1 class="complaint-title">Produto com defeito</h1>
<div class="complaint-text">Chegou quebrado e não querem trocar</div>
<div class="company-response">Pedimos desculpas, já resolvemos.</div>
<time datetime="2026-07-20"></time>
</html>
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear():
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> ReclameAquiScraper:
    return ReclameAquiScraper()


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("Magazine Luiza") == "magazine-luiza"

    def test_accent(self) -> None:
        assert slugify("João & Maria Ltda") == "joao-maria-ltda"

    def test_special_chars(self) -> None:
        assert slugify("Casas Bahia!!!") == "casas-bahia"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_parses_complaints(self, scraper: ReclameAquiScraper) -> None:
        """3 complaint cards → 3 results with correct fields."""
        with patch.object(scraper, "_fetch_page", return_value=SAMPLE_LIST_HTML):
            with patch.object(scraper, "_has_next_page", return_value=False):
                results = await scraper.search("magazine-luiza", max_pages=1)

        assert len(results) == 3
        assert results[0]["title"] == "Produto não entregue"
        assert results[0]["status"] == "Respondida"
        assert results[0]["complaint_url"] == "https://www.reclameaqui.com.br/reclamacao/123"
        assert results[1]["title"] == "Cobrança indevida"
        assert results[2]["title"] == "Atendimento ruim"
        assert results[2]["status"] == "Em tratamento"

    async def test_empty_results(self, scraper: ReclameAquiScraper) -> None:
        """Empty page → []."""
        with patch.object(scraper, "_fetch_page", return_value=SAMPLE_EMPTY_HTML):
            results = await scraper.search("unknown", max_pages=1)
        assert results == []

    async def test_fetch_returns_none(self, scraper: ReclameAquiScraper) -> None:
        """Fetch failure → []."""
        with patch.object(scraper, "_fetch_page", return_value=None):
            results = await scraper.search("error", max_pages=1)
        assert results == []


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    async def test_goes_to_next_page(self, scraper: ReclameAquiScraper) -> None:
        """Page 1 with next link + page 2 → 2 pages scraped."""
        PAGE1 = """
        <div class="complaint-card"><h2 class="complaint-card__title">
          <a href="/r/1">Produto A</a></h2>
          <a class="next" href="?p=2">Próxima</a>
        </div>
        """
        PAGE2 = """
        <div class="complaint-card"><h2 class="complaint-card__title">
          <a href="/r/2">Produto B</a></h2>
        </div>
        """
        pages = iter([PAGE1, PAGE2])

        with patch.object(scraper, "_fetch_page", side_effect=lambda u: next(pages)):
            with patch.object(scraper, "_rate_limit"):
                results = await scraper.search("test", max_pages=2)

        assert len(results) == 2  # 1 + 1 (different titles)

    async def test_stops_after_max_pages(self, scraper: ReclameAquiScraper) -> None:
        """max_pages=1 → only 1 page."""
        with patch.object(scraper, "_fetch_page", return_value=SAMPLE_LIST_HTML):
            with patch.object(scraper, "_has_next_page", return_value=True):
                with patch.object(scraper, "_rate_limit"):
                    results = await scraper.search("test", max_pages=1)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


class TestExtract:
    async def test_extract_complaint(self, scraper: ReclameAquiScraper) -> None:
        """Detail page → full complaint data."""
        with patch.object(scraper, "_fetch_page", return_value=SAMPLE_DETAIL_HTML):
            result = await scraper.extract("https://www.reclameaqui.com.br/reclamacao/123")

        assert result.get("title") == "Produto com defeito"
        assert result.get("text") == "Chegou quebrado e não querem trocar"
        assert "desculpas" in (result.get("company_response") or "")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_complaint_defaults(self) -> None:
        c = Complaint(title="Teste")
        assert c.title == "Teste"
        assert c.text is None
        assert c.rating is None

    def test_company_report(self) -> None:
        c = Complaint(title="Test")
        r = CompanyReport(company_name="Nubank", company_slug="nubank", complaints=[c])
        assert r.company_name == "Nubank"
        assert r.total_complaints == 0


# ---------------------------------------------------------------------------
# Plugin dry-run
# ---------------------------------------------------------------------------


class TestPluginDryRun:
    def test_config_loads(self) -> None:
        from src.config_manager import ConfigManager

        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_reclame_aqui")

        assert config.client_id == "demo_reclame_aqui"
        assert config.settings.get("company_slug") == "magazine-luiza"
        assert config.settings.get("max_pages") == 3
