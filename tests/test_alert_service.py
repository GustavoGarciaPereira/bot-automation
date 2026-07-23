"""Tests for alert service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.alert_service import AlertService


class TestAlertService:
    def test_send_email_no_config(self) -> None:
        svc = AlertService()
        svc._smtp_host = None  # simulate no config
        result = svc.send_email("to@test.com", "Sub", "Body")
        assert result is False  # graceful

    def test_send_telegram_no_config(self) -> None:
        svc = AlertService()
        svc._telegram_token = None
        result = svc.send_telegram("Hello")
        assert result is False

    @patch("smtplib.SMTP")
    def test_send_email_success(self, mock_smtp: MagicMock) -> None:
        svc = AlertService()
        svc._smtp_host = "smtp.test.com"
        svc._smtp_user = "user@test.com"
        svc._smtp_pass = "pass"
        result = svc.send_email("to@test.com", "Sub", "Body")
        assert result is True
        mock_smtp.assert_called_once()

    @patch("requests.post")
    def test_send_telegram_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        svc = AlertService()
        svc._telegram_token = "token"
        svc._telegram_chat_id = "123"
        result = svc.send_telegram("Hello")
        assert result is True
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_send_webhook(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        svc = AlertService()
        result = svc.send_webhook("https://hook.test.com", {"key": "val"})
        assert result is True
        mock_post.assert_called_once()

    def test_send_alert_no_channels(self) -> None:
        """No channels configured → returns empty dict."""
        svc = AlertService()
        svc._smtp_host = None
        svc._telegram_token = None
        result = svc.send_alert("Sub", "Body")
        assert isinstance(result, dict)
        assert "email" not in result
        assert "telegram" not in result
