"""Main orchestrator — runs the full RPA pipeline for a single client.

Pipeline:
1. Load client config + classification rules.
2. For each platform × user, run the plugin.
3. Classify every record.
4. Write unified Excel.
5. Email the report (if configured).
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from src.config_manager import ConfigManager
from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, ClienteConfig, IntimacaoRecord, PortalType
from src.services.classifier_service import HybridClassifier
from src.services.excel_writer import ExcelWriter
from src.services.llm_client import LLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Plugin registry — map PortalType → "module.path:ClassName"
# Extend this when adding new platforms.
# ---------------------------------------------------------------------------

PLUGIN_REGISTRY: dict[PortalType, str] = {
    PortalType.MERCADO_LIVRE: "src.plugins.mercado_livre.plugin.MercadoLivrePlugin",
    PortalType.GOOGLE_MAPS: "src.plugins.google_maps.plugin.GoogleMapsPlugin",
    PortalType.GOOGLE_SHOPPING: "src.plugins.google_shopping.plugin.GoogleShoppingPlugin",
}


class RPAOrchestrator:
    """Run the complete capture → classify → write pipeline for one client."""

    def __init__(
        self,
        client_id: str,
        *,
        headless: bool = True,
        remote_selenium_url: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.client_id = client_id
        self.headless = headless
        self.remote_selenium_url = remote_selenium_url
        self.dry_run = dry_run

        # Load config
        self.config = ConfigManager.get_client_config(client_id)

        # Services
        self.llm_client = LLMClient.from_env()
        self.classifier = HybridClassifier(llm_client=self.llm_client)
        self.classifier.load_rules(self.config)
        self.writer = ExcelWriter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> str:
        """Execute the full pipeline and return the output Excel path."""
        started = datetime.now()

        if self.dry_run:
            logger.info(
                "DRY RUN — client=%s | platforms=%s",
                self.client_id,
                [p.value for p in self.config.portais_ativos],
            )
            print(
                f"\n✓ DRY RUN — {self.client_id}: "
                f"{len(self.config.portais_ativos)} platform(s) configured"
            )
            return ""

        logger.info(
            "Pipeline started | client=%s | lawyers=%d | platforms=%d",
            self.client_id,
            len(self.config.advogados),
            len(self.config.portais_ativos),
        )

        all_records: list[IntimacaoRecord] = []
        data_ref = datetime.now().strftime("%Y-%m-%d")

        # ---- For each user × platform ----------------------------------
        for advogado in self.config.advogados:
            for portal_type in self.config.portais_ativos:
                try:
                    records = await self._run_portal(advogado, portal_type, data_ref)
                    all_records.extend(records)
                except Exception as exc:
                    logger.error(
                        "Platform %s failed for %s: %s",
                        portal_type.value,
                        advogado.nome,
                        exc,
                        extra={"portal": portal_type.value, "advogado": advogado.nome},
                    )
                    # Continue with next platform — never crash the whole pipeline

        # ---- Classify ------------------------------------------------
        await self._classify_all(all_records)

        # ---- Write Excel ---------------------------------------------
        output_path = await self.writer.write_records(
            all_records, self.client_id, data_ref
        )

        # ---- Email ---------------------------------------------------
        if output_path and self.config.emails_destino:
            await self._send_email_report(output_path)

        elapsed = (datetime.now() - started).total_seconds()
        logger.info(
            "Pipeline finished | records=%d | elapsed=%.1fs | output=%s",
            len(all_records),
            elapsed,
            output_path or "(empty)",
        )

        return output_path

    # ------------------------------------------------------------------
    # Per-platform execution
    # ------------------------------------------------------------------

    async def _run_portal(
        self,
        advogado: Advogado,
        portal_type: PortalType,
        data_ref: str,
    ) -> list[IntimacaoRecord]:
        """Instantiate plugin, authenticate, fetch, process, act."""
        plugin = self._load_plugin(portal_type)

        try:
            # 1. Authenticate
            logger.info(
                "→ %s | %s | authenticating …",
                advogado.nome,
                portal_type.value,
            )
            ok = await plugin.authenticate(advogado, self.config.model_dump())
            if not ok:
                logger.warning(
                    "Authentication returned False for %s @ %s",
                    advogado.nome,
                    portal_type.value,
                )
                return []

            # 2. Fetch
            raw_list = await plugin.fetch_intimations(advogado, data_ref)
            logger.info(
                "→ %s | %s | fetched %d raw records",
                advogado.nome,
                portal_type.value,
                len(raw_list),
            )

            # 3. Process + Act
            records: list[IntimacaoRecord] = []
            for raw in raw_list:
                record = await plugin.process_intimation(raw, advogado)
                try:
                    await plugin.take_action(record, advogado)
                except Exception as exc:
                    logger.warning(
                        "Action failed for record: %s",
                        exc,
                    )
                    record.status_registro = "Erro"
                records.append(record)

            return records

        finally:
            await plugin.cleanup()

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    async def _classify_all(self, records: list[IntimacaoRecord]) -> None:
        """Run the hybrid classifier on every record concurrently."""
        if not records:
            return

        async def _classify_one(r: IntimacaoRecord) -> None:
            destino, conf = await self.classifier.classify(r)
            r.destinatario = destino
            r.classification_confidence = conf

            if destino == "CLASSIFICACAO_MANUAL":
                r.status_registro = "Conferir"
            elif r.status_registro == "Pendente":
                r.status_registro = "Sucesso"

        tasks = [_classify_one(r) for r in records]
        await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    async def _send_email_report(self, attachment_path: str) -> None:
        """Send the report via SMTP."""
        if not self.config.email_config:
            logger.info("No email_config — skipping email")
            return

        import smtplib

        from src.security.credential_vault import CredentialVault

        cfg = self.config.email_config
        password = CredentialVault.get_secret(cfg.sender_password_ref)

        msg = MIMEMultipart()
        msg["From"] = cfg.sender_email
        msg["To"] = ", ".join(self.config.emails_destino)
        msg["Subject"] = (
            f"[RPA] Relatório — {self.config.nome_escritorio} "
            f"({datetime.now().strftime('%d/%m/%Y')})"
        )

        msg.attach(
            MIMEText(
                f"Relatório de dados extraídos para {self.config.nome_escritorio}.\n\n"
                f"Cliente: {self.client_id}\n"
                f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                "Este e-mail foi gerado automaticamente pelo Autobot RPA.",
                "plain",
            )
        )

        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
            part["Content-Disposition"] = (
                f'attachment; filename="{Path(attachment_path).name}"'
            )
            msg.attach(part)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: _smtp_send(cfg.smtp_host, cfg.smtp_port, cfg.use_tls,
                               cfg.sender_email, password,
                               self.config.emails_destino, msg),
        )

        logger.info("Email sent to %s", self.config.emails_destino)

    # ------------------------------------------------------------------
    # Plugin loader
    # ------------------------------------------------------------------

    def _load_plugin(self, portal_type: PortalType) -> PortalPlugin:
        """Dynamic import of a plugin class from the registry."""
        fqdn = PLUGIN_REGISTRY.get(portal_type)
        if fqdn is None:
            raise ValueError(
                f"No plugin registered for {portal_type.value}. "
                f"Add it to PLUGIN_REGISTRY in orchestrator.py."
            )

        module_path, class_name = fqdn.rsplit(".", 1)
        module = importlib.import_module(module_path)
        plugin_cls = getattr(module, class_name)

        return plugin_cls(
            headless=self.headless,
            remote_url=self.remote_selenium_url,
        )


# -----------------------------------------------------------------------
# Synchronous SMTP helper (runs in executor)
# -----------------------------------------------------------------------

def _smtp_send(
    host: str,
    port: int,
    use_tls: bool,
    user: str,
    password: str,
    recipients: list[str],
    msg: MIMEMultipart,
) -> None:
    import smtplib

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())
