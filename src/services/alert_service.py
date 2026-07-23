"""Alert service: sends notifications via email, Telegram, or webhook."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class AlertService:
    """Sends alerts via multiple channels. Graceful if not configured."""

    def __init__(self) -> None:
        self._smtp_host = os.getenv("SMTP_HOST")
        self._smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self._smtp_user = os.getenv("SMTP_USER")
        self._smtp_pass = os.getenv("SMTP_PASS")
        self._telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self._telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def send_email(self, to: str, subject: str, body: str) -> bool:
        if not all([self._smtp_host, self._smtp_user, self._smtp_pass]):
            logger.warning("SMTP not configured — skipping email alert")
            return False
        try:
            msg = MIMEMultipart()
            msg["From"] = self._smtp_user
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._smtp_user, self._smtp_pass)
                server.send_message(msg)
            logger.info("Email alert sent to %s", to)
            return True
        except Exception as e:
            logger.error("Email alert failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def send_telegram(self, message: str) -> bool:
        if not all([self._telegram_token, self._telegram_chat_id]):
            logger.warning("Telegram not configured — skipping alert")
            return False
        try:
            import requests

            url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
            resp = requests.post(
                url,
                json={
                    "chat_id": self._telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Telegram alert sent")
                return True
            logger.error("Telegram alert failed: %s", resp.text)
            return False
        except Exception as e:
            logger.error("Telegram alert failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    def send_webhook(self, url: str, payload: dict) -> bool:
        try:
            import requests

            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code < 400
        except Exception as e:
            logger.error("Webhook alert failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Smart alert
    # ------------------------------------------------------------------

    def send_alert(
        self, subject: str, body: str, channels: list[str] | None = None
    ) -> dict[str, bool]:
        """Send to all configured channels (or specified ones)."""
        channels = channels or ["email", "telegram"]
        results: dict[str, bool] = {}
        if "email" in channels and self._smtp_user:
            results["email"] = self.send_email(self._smtp_user, subject, body)
        if "telegram" in channels and self._telegram_token:
            results["telegram"] = self.send_telegram(f"<b>{subject}</b>\n\n{body}")
        return results
