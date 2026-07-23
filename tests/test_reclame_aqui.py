"""Unit tests for the Reclame Aqui plugin.

All Selenium calls are mocked — no real browser is launched.
Uses BeautifulSoup-based mocks matching the scraper's CSS selectors.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.plugins.reclame_aqui.models import Complaint, CompanyReport
from src.plugins.reclame_aqui.scraper import (
    ReclameAquiScraper,
    _clear_config_cache,
    slugify,
)


def _card_html(
    title: str = "Produto não entregue",
    url: str = "/reclamacao/123",
    date: str = "2026-07-15",
    status: str = "Respondida",
    text: str = "Pedido não entregue no prazo.",
) -> str:
    return (
        f'<div class="complaint-card">'
        f'<a href="{url}">{title}</a>'
        f'<time datetime="{date}">{date}</time>'
        f'<span class="status">{status}</span>'
        f'<p class="text">{text}</p>'
        f'</div>'
    )


def _make_item(html: str) -> MagicMock:
    """Mock Selenium element backed by realistic HTML."""
    item = MagicMock()
    soup = BeautifulSoup(html, "html.parser")

    def _find(by: str, selector: str) -> MagicMock:
        tag = soup.select_one(selector)
        if tag is None:
            raise Exception(f"Not found: {selector}")
        m = MagicMock()
        m.text = tag.text.strip()
        attrs = {}
        for a in ("href", "datetime", "class"):
            v = tag.get(a)
            if v:
                attrs[a] = v
        if attrs:
            m.get_attribute.side_effect = lambda k: attrs.get(k, "")
        else:
            m.get_attribute.return_value = ""
        return m

    def _find_elems(by: str, selector: str) -> list[MagicMock]:
        return []

    item.find_element.side_effect = _find
    item.find_elements.side_effect = _find_elems
    item.text = soup.get_text("\n", strip=True)
    return item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear():
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> ReclameAquiScraper:
    return ReclameAquiScraper(headless=True)


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("Magazine Luiza") == "magazine-luiza-loja-online"

    def test_accent(self) -> None:
        assert slugify("João & Maria Ltda") == "joao-maria-ltda"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_parses_complaints(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: ReclameAquiScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _make_item(_card_html(title="Problema A", status="Respondida")),
            _make_item(_card_html(title="Problema B", status="Não respondida")),
            _make_item(_card_html(title="Problema C", status="Em tratamento")),
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("magazine-luiza-loja-online", max_pages=1)

        assert len(results) == 3
        assert results[0]["title"] == "Problema A"
        assert results[2]["status"] == "Em tratamento"

    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_empty_results(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: ReclameAquiScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_driver.find_elements.return_value = []

        results = await scraper.search("x", max_pages=1)
        assert results == []


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_no_next_page(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: ReclameAquiScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [_make_item(_card_html(title="Unique"))]
        mock_driver.find_elements.return_value = mock_items
        mock_driver.find_element.side_effect = Exception("no next page")

        results = await scraper.search("test", max_pages=3)
        assert len(results) == 1  # only page 1


# ---------------------------------------------------------------------------
# Scroll
# ---------------------------------------------------------------------------


class TestScroll:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_scroll_called(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: ReclameAquiScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [_make_item(_card_html(title="T"))]
        mock_driver.find_elements.return_value = mock_items

        await scraper.search("test", max_pages=1)
        assert mock_driver.execute_script.call_count >= 1


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


class TestExtract:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_extract(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: ReclameAquiScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        # Build page HTML and use BeautifulSoup-based mock
        html = (
            '<h1 class="complaint-title">Produto com defeito</h1>'
            '<div class="complaint-text">Chegou quebrado</div>'
        )
        soup = BeautifulSoup(html, "html.parser")

        def _find(by: str, selector: str) -> MagicMock:
            tag = soup.select_one(selector)
            if tag is None:
                raise Exception(f"Not found: {selector}")
            m = MagicMock()
            m.text = tag.text.strip()
            return m

        mock_driver.find_element.side_effect = _find
        mock_driver.find_elements.return_value = []

        result = await scraper.extract("https://www.reclameaqui.com.br/r/123")
        assert result.get("title") == "Produto com defeito"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_complaint_defaults(self) -> None:
        c = Complaint(title="Teste")
        assert c.title == "Teste"
        assert c.text is None

    def test_company_report(self) -> None:
        c = Complaint(title="T")
        r = CompanyReport(company_name="Nubank", company_slug="nubank", complaints=[c])
        assert r.company_name == "Nubank"


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


class TestPluginDryRun:
    def test_config_loads(self) -> None:
        from src.config_manager import ConfigManager
        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_reclame_aqui")
        assert config.client_id == "demo_reclame_aqui"
        assert config.settings.get("company_slug") == "magazine-luiza-loja-online"
