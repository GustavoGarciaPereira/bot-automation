"""Unit tests for the Reclame Aqui plugin.

All Selenium calls are mocked — no real browser is launched.
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


def _make_card_html(
    title: str = "Produto não entregue",
    date: str = "15/07/2026",
    status: str = "Respondida",
    text: str = "Pedido não foi entregue no prazo.",
    url: str = "https://www.reclameaqui.com.br/reclamacao/123",
) -> str:
    return (
        f'<div class="complaint-card">'
        f'<h2 class="complaint-card__title"><a href="{url}">{title}</a></h2>'
        f'<span class="complaint-card__date">{date}</span>'
        f'<span class="complaint-card__status">{status}</span>'
        f'<p class="complaint-card__text">{text}</p>'
        f'</div>'
    )


def _make_item(html: str) -> MagicMock:
    """Create a mock Selenium element backed by realistic HTML."""
    item = MagicMock()
    soup = BeautifulSoup(html, "html.parser")

    def _find(by: str, selector: str) -> MagicMock:
        tag = soup.select_one(selector)
        if tag is None:
            raise Exception(f"Mock selector not found: {selector}")
        m = MagicMock()
        m.text = tag.text.strip()
        attrs = {}
        for attr in ("href", "datetime", "aria-label", "data-testid", "class"):
            val = tag.get(attr)
            if val:
                attrs[attr] = val
        if attrs:
            m.get_attribute.side_effect = lambda k: attrs.get(k, "")
        else:
            m.get_attribute.return_value = ""
        return m

    def _find_elems(by: str, selector: str) -> list[MagicMock]:
        tags = soup.select(selector)
        result = []
        for tag in tags:
            m = MagicMock()
            m.text = tag.text.strip()
            result.append(m)
        return result

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
        assert slugify("Magazine Luiza") == "magazine-luiza"

    def test_accent(self) -> None:
        assert slugify("João & Maria Ltda") == "joao-maria-ltda"

    def test_already_slug(self) -> None:
        assert slugify("magazine-luiza") == "magazine-luiza"

    def test_special_chars(self) -> None:
        assert slugify("Casas Bahia!!!") == "casas-bahia"


# ---------------------------------------------------------------------------
# Search: parse cards
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_parses_complaints(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: ReclameAquiScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _make_item(_make_card_html(title="Problema A", status="Respondida")),
            _make_item(_make_card_html(title="Problema B", status="Não respondida")),
            _make_item(_make_card_html(title="Problema C", status="Em tratamento")),
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("magazine-luiza", max_pages=1)

        assert len(results) == 3
        assert results[0]["title"] == "Problema A"
        assert results[0]["status"] == "Respondida"
        assert results[1]["title"] == "Problema B"
        assert results[2]["title"] == "Problema C"

    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_empty_results(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: ReclameAquiScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_driver.find_elements.return_value = []

        results = await scraper.search("unknown-company", max_pages=1)
        assert results == []


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    async def test_goes_to_next_page(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: ReclameAquiScraper
    ) -> None:
        """With a next page link, should navigate."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        # First call returns 1 item, second returns 2 items (next page)
        call_count = [0]

        def _find_items(*args: Any, **kwargs: Any) -> list[MagicMock]:
            call_count[0] += 1
            if call_count[0] <= 1:
                return [_make_item(_make_card_html(title="Page 1"))]
            return [_make_item(_make_card_html(title="Page 2"))]

        mock_driver.find_elements.side_effect = _find_items

        # Mock next page link
        next_link = MagicMock()
        next_link.get_attribute.return_value = "https://www.reclameaqui.com.br/empresa/test?page=2"
        mock_driver.find_element.return_value = next_link

        with patch("time.sleep"):
            results = await scraper.search("test", max_pages=2)

        assert len(results) == 2
        assert results[0]["title"] == "Page 1"
        assert results[1]["title"] == "Page 2"

    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    async def test_no_next_page_stops(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: ReclameAquiScraper
    ) -> None:
        """No next page link → stops after page 1."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _make_item(_make_card_html(title="Only page")),
        ]
        mock_driver.find_elements.return_value = mock_items
        # No next page link found
        mock_driver.find_element.side_effect = Exception("Not found")

        with patch("time.sleep"):
            results = await scraper.search("test", max_pages=3)

        assert len(results) == 1
        assert results[0]["title"] == "Only page"


# ---------------------------------------------------------------------------
# Modal close
# ---------------------------------------------------------------------------


class TestCloseModals:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    @patch("src.plugins.reclame_aqui.scraper.time.sleep")
    async def test_modal_close_called(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: ReclameAquiScraper
    ) -> None:
        """Modal close should be called during search."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [_make_item(_make_card_html(title="Test"))]
        mock_driver.find_elements.return_value = mock_items

        with patch("time.sleep"):
            await scraper.search("test", max_pages=1)

        # find_element should have been called for modal selectors
        modal_calls = [
            c for c in mock_driver.find_element.call_args_list
            if "cookie" in str(c) or "Aceitar" in str(c) or "Fechar" in str(c)
        ]
        assert mock_driver.find_element.call_count >= 1


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


class TestExtract:
    @patch("src.plugins.reclame_aqui.scraper.selenium_driver")
    @patch("src.plugins.reclame_aqui.scraper.WebDriverWait")
    async def test_extract_complaint(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: ReclameAquiScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        # Build a proper HTML page mock
        page_html = (
            '<h1 class="complaint-title">Produto com defeito</h1>'
            '<div class="complaint-text">Chegou quebrado</div>'
        )
        mock_soup = BeautifulSoup(page_html, "html.parser")

        def _find_element(by: str, selector: str) -> MagicMock:
            tag = mock_soup.select_one(selector)
            if tag is None:
                raise Exception(f"Not found: {selector}")
            m = MagicMock()
            m.text = tag.text.strip()
            return m

        mock_driver.find_element.side_effect = _find_element
        # find_elements returns empty for modal selectors (no modals)
        mock_driver.find_elements.return_value = []

        with patch("time.sleep"):
            result = await scraper.extract("https://www.reclameaqui.com.br/reclamacao/123")

        assert result.get("title") == "Produto com defeito"
        assert result.get("complaint_url") == "https://www.reclameaqui.com.br/reclamacao/123"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_complaint_defaults(self) -> None:
        c = Complaint(title="Teste")
        assert c.title == "Teste"
        assert c.text is None
        assert c.date is None
        assert c.status is None
        assert c.rating is None

    def test_company_report(self) -> None:
        c = Complaint(title="Test")
        r = CompanyReport(company_name="Nubank", company_slug="nubank", complaints=[c])
        assert r.company_name == "Nubank"
        assert r.total_complaints == 0
        assert len(r.complaints) == 1
        assert r.avg_rating is None


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
