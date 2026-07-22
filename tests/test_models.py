"""Unit tests for Pydantic data models."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError

from src.models import Advogado, ClienteConfig, IntimacaoRecord, PortalType


# ---------------------------------------------------------------------------
# Advogado
# ---------------------------------------------------------------------------

class TestAdvogado:
    def test_minimal_valid(self) -> None:
        a = Advogado(nome="Dr. Silva", senha_ref="VAULT:SENHA")
        assert a.nome == "Dr. Silva"
        assert a.senha_ref == "VAULT:SENHA"
        assert a.certificado_path is None
        assert a.usuario is None
        assert a.email_2fa is None

    def test_nome_too_short_raises(self) -> None:
        with pytest.raises(ValidationError):
            Advogado(nome="X", senha_ref="VAULT:X")

    def test_nome_missing_raises(self) -> None:
        with pytest.raises(ValidationError):
            Advogado(senha_ref="VAULT:X")  # type: ignore[arg-type]

    def test_certificado_missing_file_raises(self) -> None:
        with pytest.raises(ValidationError, match="Certificate file not found"):
            Advogado(
                nome="Dr. Silva",
                senha_ref="VAULT:X",
                certificado_path="/nonexistent/cert.pfx",
            )

    def test_certificado_valid_path(self) -> None:
        with TemporaryDirectory() as tmp:
            cert = Path(tmp) / "test.pfx"
            cert.write_text("dummy")
            a = Advogado(
                nome="Dr. Silva",
                senha_ref="VAULT:X",
                certificado_path=str(cert),
            )
            assert a.certificado_path == str(cert)


# ---------------------------------------------------------------------------
# IntimacaoRecord
# ---------------------------------------------------------------------------

class TestIntimacaoRecord:
    def test_defaults(self) -> None:
        r = IntimacaoRecord(portal="mercado_livre", advogado="Dr. Silva")
        assert r.portal == "mercado_livre"
        assert r.advogado == "Dr. Silva"
        assert r.status_registro == "Pendente"
        assert r.data_consulta != ""
        assert r.destinatario is None
        assert r.classification_confidence is None

    def test_confidence_bounds(self) -> None:
        r = IntimacaoRecord(
            portal="p", advogado="a", classification_confidence=0.5
        )
        assert r.classification_confidence == 0.5

    def test_confidence_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            IntimacaoRecord(
                portal="p", advogado="a", classification_confidence=-0.1
            )

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(ValidationError):
            IntimacaoRecord(
                portal="p", advogado="a", classification_confidence=1.5
            )

    def test_model_dump_excludes_raw_data(self) -> None:
        r = IntimacaoRecord(
            portal="p", advogado="a", raw_data={"secret": "xyz"}
        )
        dumped = r.model_dump()
        assert "raw_data" not in dumped


# ---------------------------------------------------------------------------
# ClienteConfig
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = {
    "client_id": "test_client",
    "nome_escritorio": "Test Office",
    "advogados": [
        {"nome": "Dr. A", "senha_ref": "VAULT:A"},
        {"nome": "Dr. B", "senha_ref": "VAULT:B"},
    ],
    "portais_ativos": ["mercado_livre", "google_maps"],
    "emails_destino": ["to@example.com"],
    "classification_rules": {"notebook": "Informática", "iphone": "Celulares"},
}


class TestClienteConfig:
    def test_valid_config(self) -> None:
        cfg = ClienteConfig.model_validate(SAMPLE_CONFIG)
        assert cfg.client_id == "test_client"
        assert len(cfg.advogados) == 2
        assert len(cfg.portais_ativos) == 2
        assert cfg.use_ai_classifier is True
        assert cfg.ai_fallback_threshold == 0.8

    def test_no_advogados_raises(self) -> None:
        data = {**SAMPLE_CONFIG, "advogados": []}
        with pytest.raises(ValidationError):
            ClienteConfig.model_validate(data)

    def test_no_portais_raises(self) -> None:
        data = {**SAMPLE_CONFIG, "portais_ativos": []}
        with pytest.raises(ValidationError):
            ClienteConfig.model_validate(data)

    def test_no_emails_raises(self) -> None:
        data = {**SAMPLE_CONFIG, "emails_destino": []}
        with pytest.raises(ValidationError):
            ClienteConfig.model_validate(data)

    def test_client_id_pattern(self) -> None:
        data = {**SAMPLE_CONFIG, "client_id": "Invalid ID!"}
        with pytest.raises(ValidationError):
            ClienteConfig.model_validate(data)

    def test_load_from_file(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "test_client.json"
            cfg_path.write_text(json.dumps(SAMPLE_CONFIG), encoding="utf-8")

            cfg = ClienteConfig.load("test_client", configs_dir=str(tmp))
            assert cfg.client_id == "test_client"
            assert cfg.nome_escritorio == "Test Office"

    def test_load_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            ClienteConfig.load("nonexistent", configs_dir="/tmp/nope")

    def test_cache(self) -> None:
        ClienteConfig.clear_cache()
        with TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "cached.json"
            cfg_path.write_text(json.dumps(SAMPLE_CONFIG), encoding="utf-8")

            a = ClienteConfig.load("cached", configs_dir=str(tmp))
            b = ClienteConfig.load("cached", configs_dir=str(tmp))
            assert a is b  # same object from cache


# ---------------------------------------------------------------------------
# PortalType enum
# ---------------------------------------------------------------------------

class TestPortalType:
    def test_all_values_are_strings(self) -> None:
        for pt in PortalType:
            assert isinstance(pt.value, str)
            assert pt.value == pt.value.lower()
