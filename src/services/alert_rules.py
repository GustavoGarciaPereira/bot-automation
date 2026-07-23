"""Alert rules: conditions that trigger notifications."""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertRules:
    """Evaluates data and generates alerts based on rules."""

    def __init__(self, alert_service: object) -> None:
        self._alert = alert_service

    def check_ml_price_drops(
        self, products: list[dict], threshold_pct: float = 10.0
    ) -> list[str]:
        """Alert if product price dropped significantly."""
        alerts: list[str] = []
        for p in products:
            original = p.get("original_price")
            current = p.get("price")
            if original and current and original > 0:
                drop_pct = ((original - current) / original) * 100
                if drop_pct >= threshold_pct:
                    alerts.append(
                        f"📉 <b>{p['title'][:50]}</b>\n"
                        f"   Preço caiu {drop_pct:.1f}%: "
                        f"R$ {original:.2f} → R$ {current:.2f}"
                    )
        if alerts:
            body = "\n\n".join(alerts)
            self._alert.send_alert(
                subject=f"🚨 {len(alerts)} queda(s) de preço detectada(s)",
                body=body,
            )
        return alerts

    def check_olx_urgent(self, ads: list[dict]) -> list[dict]:
        """Alert for urgent OLX ads."""
        urgent = [a for a in ads if a.get("ai_urgency") == "urgente"]
        if urgent:
            body = "\n\n".join(
                f"⚡ <b>{a['title'][:50]}</b>\n"
                f"   R$ {a.get('price', 'N/A')} | {a.get('location', 'N/A')}"
                for a in urgent
            )
            self._alert.send_alert(
                subject=f"⚡ {len(urgent)} anúncio(s) urgente(s) na OLX",
                body=body,
            )
        return urgent

    def check_maps_high_leads(self, businesses: list[dict]) -> list[dict]:
        """Alert for high-potential leads."""
        high = [b for b in businesses if b.get("ai_lead_potential") == "alto"]
        if high:
            body = "\n\n".join(
                f"🎯 <b>{b['name'][:50]}</b>\n"
                f"   ⭐ {b.get('rating', 'N/A')} | 📍 {b.get('address', 'N/A')}\n"
                f"   Motivo: {b.get('ai_lead_reason', 'N/A')}"
                for b in high
            )
            self._alert.send_alert(
                subject=f"🎯 {len(high)} lead(s) de alto potencial encontrado(s)",
                body=body,
            )
        return high

    def send_summary(self, plugin_name: str, data: list[dict]) -> None:
        """Send execution summary."""
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        body = (
            f"📊 <b>Resumo da execução</b>\n\n"
            f"Plugin: {plugin_name}\n"
            f"Itens extraídos: {len(data)}\n"
            f"Horário: {now}\n"
        )
        ai_classified = sum(1 for d in data if d.get("ai_category"))
        if ai_classified:
            body += f"Classificados com IA: {ai_classified}/{len(data)}\n"
        self._alert.send_alert(
            subject=f"✅ Autobot: {len(data)} itens de {plugin_name}",
            body=body,
        )
