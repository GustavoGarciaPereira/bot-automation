"""Pydantic v2 data models for the Autobot RPA system.

All domain entities are defined here with full validation.
No client-specific values are hardcoded — everything is driven by
external JSON configuration.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PortalType(str, Enum):
    """Supported platform identifiers — extend as new plugins are added."""

    MERCADO_LIVRE = "mercado_livre"
    GOOGLE_MAPS = "google_maps"
    CONSUMIDOR_GOV = "consumidor_gov"


class RecordStatus(str, Enum):
    PENDENTE = "Pendente"
    SUCESSO = "Sucesso"
    CONFERIR = "Conferir"
    ERRO = "Erro"
    IGNORADO = "Ignorado"


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

class Advogado(BaseModel):
    """A lawyer / authorised person whose credentials are used to access
    justice portals on behalf of a client firm."""

    nome: str = Field(..., min_length=2, description="Full name of the lawyer")
    certificado_path: str | None = Field(
        None, description="Filesystem path to the .pfx digital certificate"
    )
    usuario: str | None = Field(
        None, description="Portal username (when applicable)"
    )
    senha_ref: str = Field(
        ...,
        description="Reference key for the CredentialVault — never the raw password",
    )
    email_2fa: str | None = Field(
        None, description="Email address that receives 2FA codes"
    )

    @field_validator("certificado_path")
    @classmethod
    def _certificado_must_exist_if_set(cls, v: str | None) -> str | None:
        if v is not None and not Path(v).exists():
            raise ValueError(f"Certificate file not found: {v}")
        return v


class EmailConfig(BaseModel):
    """SMTP settings for delivering the final Excel report."""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_email: str = Field(..., description="From address")
    sender_password_ref: str = Field(
        ..., description="Vault reference for the SMTP password"
    )
    use_tls: bool = True


class ClienteConfig(BaseModel):
    """Top-level configuration loaded from clients/<client_id>.json."""

    client_id: str = Field(..., min_length=2, pattern=r"^[a-z0-9_]+$")
    nome_escritorio: str = Field(..., min_length=2)
    advogados: list[Advogado] = Field(..., min_length=1)
    portais_ativos: list[PortalType] = Field(..., min_length=1)
    emails_destino: list[str] = Field(..., min_length=1)
    email_config: EmailConfig | None = None

    use_ai_classifier: bool = True
    ai_fallback_threshold: float = Field(
        0.8, ge=0.0, le=1.0, description="Minimum confidence to accept AI answer"
    )

    classification_rules: dict[str, str] = Field(
        default_factory=dict,
        description="Keyword → category mapping for regex-first classification",
    )

    settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Platform-specific settings (search_terms, max_results, etc.)",
    )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    _registry: ClassVar[dict[str, ClienteConfig]] = {}

    @classmethod
    def load(cls, client_id: str, configs_dir: str = "clients") -> ClienteConfig:
        """Load, validate, cache, and return a client configuration from JSON."""
        import json

        if client_id in cls._registry:
            return cls._registry[client_id]

        path = Path(configs_dir) / f"{client_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Client config not found: {path}")

        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg = cls.model_validate(raw)
        cls._registry[client_id] = cfg
        return cfg

    @classmethod
    def clear_cache(cls) -> None:
        cls._registry.clear()


class IntimacaoRecord(BaseModel):
    """Standardised record representing one judicial intimation.

    This is the canonical output row — every portal plugin MUST map its
    raw data into this shape.
    """

    # -- Identification
    data_consulta: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d"),
        description="Date the RPA extracted this record",
    )
    portal: str = Field(..., description="PortalType value")
    advogado: str = Field(..., description="Lawyer name")
    sequencia: str = Field(default="", description="Sequential number in portal")

    # -- Core fields (nullable — not every portal provides them all)
    tipo_comunicacao: str | None = None
    numero_processo: str | None = None
    numero_movimento: str | None = None
    registro_comunicacao: str | None = None
    data_comunicacao: str | None = None
    cincia: str | None = None
    data_prazo_fatal: str | None = None
    objeto_comunicacao: str | None = None
    destinatario: str | None = None
    instancia: str | None = None
    comarca: str | None = None
    parte_1: str | None = None

    # -- Processing metadata
    status_registro: str = RecordStatus.PENDENTE.value
    despacho: str | None = None
    classification_confidence: float | None = Field(None, ge=0.0, le=1.0)

    # -- Raw payload preserved for audit / debugging
    raw_data: dict[str, Any] = Field(default_factory=dict, exclude=True)
