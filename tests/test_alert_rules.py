"""Tests for alert rules."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services.alert_rules import AlertRules


@pytest.fixture
def mock_alert() -> MagicMock:
    return MagicMock()


class TestAlertRules:
    def test_price_drop_alert(self, mock_alert: MagicMock) -> None:
        rules = AlertRules(mock_alert)
        products = [{"title": "Notebook", "original_price": 100.0, "price": 80.0}]
        alerts = rules.check_ml_price_drops(products, threshold_pct=10.0)
        assert len(alerts) == 1  # 20% drop > 10%
        mock_alert.send_alert.assert_called_once()

    def test_price_no_drop(self, mock_alert: MagicMock) -> None:
        rules = AlertRules(mock_alert)
        products = [{"title": "Notebook", "original_price": 100.0, "price": 95.0}]
        alerts = rules.check_ml_price_drops(products, threshold_pct=10.0)
        assert len(alerts) == 0  # 5% drop < 10%
        mock_alert.send_alert.assert_not_called()

    def test_olx_urgent(self, mock_alert: MagicMock) -> None:
        rules = AlertRules(mock_alert)
        ads = [
            {"title": "Urgente!", "ai_urgency": "urgente"},
            {"title": "Normal", "ai_urgency": "normal"},
        ]
        urgent = rules.check_olx_urgent(ads)
        assert len(urgent) == 1
        mock_alert.send_alert.assert_called_once()

    def test_maps_high_lead(self, mock_alert: MagicMock) -> None:
        rules = AlertRules(mock_alert)
        businesses = [
            {"name": "Top", "ai_lead_potential": "alto"},
            {"name": "Low", "ai_lead_potential": "baixo"},
        ]
        high = rules.check_maps_high_leads(businesses)
        assert len(high) == 1
        mock_alert.send_alert.assert_called_once()

    def test_summary(self, mock_alert: MagicMock) -> None:
        rules = AlertRules(mock_alert)
        rules.send_summary("olx", [{"title": "A"}, {"title": "B"}])
        mock_alert.send_alert.assert_called_once()
        args = mock_alert.send_alert.call_args[1]
        assert "2 itens" in args.get("subject", "")

    def test_no_price_no_alert(self, mock_alert: MagicMock) -> None:
        """Missing original_price → no alert."""
        rules = AlertRules(mock_alert)
        products = [{"title": "Test", "price": 50.0}]  # no original_price
        alerts = rules.check_ml_price_drops(products)
        assert len(alerts) == 0
