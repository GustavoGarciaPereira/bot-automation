"""Tests for Consumidor.gov.br plugin. All Selenium calls mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.plugins.consumidor_gov.models import Complaint, CompanyStats
from src.plugins.consumidor_gov.scraper import (
    ConsumidorGovScraper,
    _clear_config_cache,
)


def _make_item(html: str) -> MagicMock:
    item = MagicMock()
    soup = BeautifulSoup(html, "html.parser")

    def _find(by: str, selector: str) -> MagicMock:
        tag = soup.select_one(selector)
        if tag is None:
            raise Exception(f"Not found: {selector}")
        m = MagicMock()
        m.text = tag.text.strip()
        return m

    item.find_element.side_effect = _find
    item.find_elements.return_value = []
    item.text = soup.get_text("\n", strip=True)
    return item


@pytest.fixture(autouse=True)
def _clear():
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> ConsumidorGovScraper:
    return ConsumidorGovScraper(headless=True)


class TestSearch:
    @patch("src.plugins.consumidor_gov.scraper.selenium_driver")
    @patch("src.plugins.consumidor_gov.scraper.WebDriverWait")
    @patch("src.plugins.consumidor_gov.scraper.time.sleep")
    async def test_search(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: ConsumidorGovScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _make_item("<table><tr><td>Problema A</td><td>15/07</td><td>Respondida</td></tr></table>"),
        ]
        mock_driver.find_elements.return_value = mock_items

        with patch.object(scraper, "_wait_for_results", return_value=True):
            with patch.object(scraper, "_go_next_page", return_value=False):
                results = await scraper.search("Test", max_pages=1)

        assert len(results) >= 1

    @patch("src.plugins.consumidor_gov.scraper.selenium_driver")
    @patch("src.plugins.consumidor_gov.scraper.WebDriverWait")
    @patch("src.plugins.consumidor_gov.scraper.time.sleep")
    async def test_empty(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: ConsumidorGovScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_driver.find_elements.return_value = []

        with patch.object(scraper, "_wait_for_results", return_value=True):
            with patch.object(scraper, "_go_next_page", return_value=False):
                results = await scraper.search("Test", max_pages=1)

        assert results == []


class TestModels:
    def test_complaint_defaults(self) -> None:
        c = Complaint(company_name="Nubank")
        assert c.company_name == "Nubank"
        assert c.title is None

    def test_company_stats(self) -> None:
        s = CompanyStats(company_name="Nubank", total_complaints=100)
        assert s.total_complaints == 100
        assert len(s.complaints) == 0


class TestDryRun:
    def test_config_loads(self) -> None:
        from src.config_manager import ConfigManager
        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_consumidor_gov")
        assert config.client_id == "demo_consumidor_gov"
        assert config.settings.get("company_name") == "Magazine Luiza"
