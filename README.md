# 🤖 Autobot RPA — Extração Genérica de Dados Multi-Plataforma

**Sistema RPA multi-tenant, 100% configurável, para extração de dados em múltiplas plataformas web.**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Pydantic](https://img.shields.io/badge/pydantic-v2-ff69b4)](https://docs.pydantic.dev/latest/)
[![Selenium](https://img.shields.io/badge/selenium-4.15%2B-green)](https://www.selenium.dev/)
[![LangChain](https://img.shields.io/badge/langchain-0.1%2B-orange)](https://www.langchain.com/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## 📖 Índice

- [Visão Geral](#-visão-geral)
- [Arquitetura](#-arquitetura)
- [Fluxo de Execução](#-fluxo-de-execução)
- [Estrutura de Pastas](#-estrutura-de-pastas)
- [Stack Tecnológica](#-stack-tecnológica)
- [Instalação](#-instalação)
- [Configuração](#-configuração)
- [Uso](#-uso)
- [Criando um Novo Plugin](#-criando-um-novo-plugin)
- [Classificação (De-Para)](#-classificação-de-para)
- [Segurança](#-segurança)
- [Docker](#-docker)
- [Testes](#-testes)
- [Logs & Debug](#-logs--debug)

---

## 🎯 Visão Geral

O **Autobot RPA** automatiza a extração de dados de múltiplas plataformas web (Mercado Livre, Google Maps, Reclame Aqui, etc.), para múltiplos clientes simultaneamente, com **zero código específico por cliente**.

### Plataformas suportadas

| Plataforma | Tipo | Plugin |
|---|---|---|
| **Mercado Livre** | E-commerce | `mercado_livre` |
| **Google Maps** | Geografia/Locais | `google_maps` |
| **Reclame Aqui** | Reclamações | `reclame_aqui` |

### Princípios Fundamentais

| Princípio | Descrição |
|---|---|
| **100% Genérico** | Nenhum nome de cliente ou plataforma está hardcoded |
| **Multi-Tenant** | Um único código-base atende N clientes (`--client-id`) |
| **Config-Driven** | Comportamento definido em JSON externo |
| **Headless** | Roda em terminal/serviço, sem interface gráfica |
| **IA como Aprimoramento** | LLM é opcional — se falhar, fallback para classificação manual |
| **Resiliente** | Erro em uma plataforma não derruba a execução inteira |

### Saída

Uma **planilha Excel unificada** (`data/output/<client_id>/records_YYYY-MM-DD.xlsx`) com colunas padronizadas, opcionalmente enviada por e-mail ao final da execução.

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI (main.py)                          │
│              argparse: --client-id, --no-headless           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   RPAOrchestrator                            │
│   Pipeline: config → plugins → classify → Excel → email     │
└──────┬──────────┬──────────┬──────────────┬─────────────────┘
       │          │          │              │
┌──────▼──┐ ┌─────▼───┐ ┌───▼──────┐ ┌─────▼──────┐
│ Config  │ │ Plugins │ │Classifier│ │ ExcelWriter │
│ Manager │ │(Adapters│ │(Hybrid)  │ │ (Pandas)    │
│ (JSON)  │ │ Selenium│ │Regex→LLM │ │             │
└─────────┘ └─────────┘ └──────────┘ └─────────────┘
```

### Padrão Hexagonal (Ports & Adapters)

```
┌──────────────────────────────────────┐
│           DOMAIN (models.py)         │
│  ClienteConfig, IntimacaoRecord,     │
│  PortalType, Advogado                │
└────────────────┬─────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼────┐ ┌─────▼────┐ ┌────▼─────┐
│ PORT   │ │  PORT    │ │  PORT    │
│Portal  │ │Classifier│ │Output    │
│Plugin  │ │          │ │Writer    │
│(ABC)   │ │(ABC)     │ │(ABC)     │
└───┬────┘ └─────┬────┘ └────┬─────┘
    │            │            │
┌───▼────────┐ ┌─▼──────────┐ ┌▼──────────┐
│ ADAPTERS   │ │ ADAPTERS   │ │ ADAPTERS  │
│ Mercado    │ │ Hybrid     │ │ Excel     │
│ Livre      │ │ Classifier │ │ Writer    │
│ Google Maps│ │ (Regex+LLM)│ │ (Pandas)  │
│ Reclame    │ │            │ │           │
│ Aqui       │ │            │ │           │
└────────────┘ └────────────┘ └───────────┘
```

---

## 🔄 Fluxo de Execução

Cada execução do RPA segue esta pipeline:

```
1. INIT        main.py carrega --client-id e o JSON correspondente
       │
2. CONFIG      ClienteConfig.load() → cache em memória
       │
3. ORCHESTRATE Para cada Advogado × Plataforma ativa:
       │
       ├─ 3a. AUTH       authenticate() → login (se necessário)
       ├─ 3b. FETCH      fetch_intimations() → lista de dicts brutos
       ├─ 3c. PROCESS    process_intimation() → IntimacaoRecord
       └─ 3d. ACTION     take_action() → ação específica da plataforma
       │
4. CLASSIFY    HybridClassifier em todos os registros (concorrente)
       │         Regex (keyword match) → LLM (DeepSeek/GPT) → MANUAL
       │
5. WRITE       ExcelWriter → data/output/<client_id>/records_<data>.xlsx
       │
6. NOTIFY      SMTP → anexa planilha e envia para emails_destino
```

---

## 📁 Estrutura de Pastas

```
autobot-rpa/
├── src/
│   ├── main.py                      # Entrypoint CLI
│   ├── orchestrator.py              # Pipeline principal
│   ├── config_manager.py            # Carregador de JSONs (com cache)
│   ├── models.py                    # Pydantic v2: todos os modelos
│   │
│   ├── interfaces/                  # 🔌 Ports (contratos abstratos)
│   │   ├── portal_plugin.py         #   ABC para plugins de plataforma
│   │   ├── scraper.py              #   ABC para scrapers (search/extract)
│   │   ├── classifier.py            #   ABC para classificadores
│   │   └── output_writer.py         #   ABC para persistência
│   │
│   ├── plugins/                     # 🔧 Adapters (implementações)
│   │   ├── base_selenium_plugin.py  #   Helpers: waits, retry, screenshots
│   │   ├── mercado_livre/           #   Plugin Mercado Livre
│   │   │   └── plugin.py
│   │   ├── google_maps/             #   Plugin Google Maps
│   │   │   └── plugin.py
│   │   └── reclame_aqui/            #   Plugin Reclame Aqui
│   │       └── plugin.py
│   │
│   ├── services/                    # 🧠 Lógica de negócio
│   │   ├── classifier_service.py    #   Hybrid: Regex → LLM → Manual
│   │   ├── llm_client.py            #   LangChain (DeepSeek/OpenAI/Azure)
│   │   └── excel_writer.py          #   Pandas + openpyxl formatado
│   │
│   ├── security/                    # 🔐 Credenciais
│   │   ├── credential_vault.py      #   Keyring → .env fallback
│   │   └── certificate_handler.py   #   Certificados .pfx/A3
│   │
│   └── utils/                       # 🛠️ Utilitários
│       ├── logger.py                #   JSON lines + rotação diária
│       └── email_2fa_handler.py     #   IMAP polling para 2FA
│
├── clients/                         # ⚙️ Configs dos clientes
│   ├── demo_mercado_livre.json      #   Config Mercado Livre
│   ├── demo_google_maps.json        #   Config Google Maps
│   └── demo_reclame_aqui.json       #   Config Reclame Aqui
│
├── tests/
│   ├── test_models.py               # Testes de validação Pydantic
│   └── test_classifier.py           # Testes do classificador híbrido
│
├── data/
│   ├── output/                      # Planilhas geradas
│   └── logs/                        # Logs JSON + screenshots de erro
│
├── requirements.txt                 # Dependências com versões fixas
├── docker-compose.yml               # Selenium Grid 4 + App
├── Dockerfile                       # Python 3.12-slim
├── pyproject.toml                   # Config pytest
├── .env                             # Variáveis de ambiente (template)
└── .gitignore
```

---

## 🧰 Stack Tecnológica

| Camada | Tecnologia | Versão |
|---|---|---|
| **Linguagem** | Python | 3.10+ |
| **Modelos** | Pydantic | 2.5+ |
| **Web Scraping** | Selenium + WebDriverWait / Requests | 4.15+ / 2.31+ |
| **IA / LLM** | LangChain + ChatOpenAI | 0.1+ |
| **Excel** | Pandas + OpenPyXL | 2.1+ / 3.1+ |
| **Credenciais** | keyring → python-dotenv | 24+ / 1.0+ |
| **Resiliência** | tenacity (exponential backoff) | 8.2+ |
| **Testes** | pytest + pytest-asyncio | 8.0+ |
| **Container** | Docker + Selenium Grid 4 | — |

---

## 🚀 Instalação

```bash
# 1. Clone o repositório
git clone <repo-url>
cd autobot-rpa

# 2. Crie o ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure o .env
cp .env .env.local
# Edite .env.local com suas chaves (DeepSeek, email, etc.)
```

---

## ⚙️ Configuração

### 1. Variáveis de Ambiente (`.env`)

```bash
# LLM — DeepSeek (recomendado, mais barato e melhor em português)
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.0

# Email — senha de app para SMTP (envio de relatórios)
EMAIL_APP_PASSWORD=your-app-password
```

### 2. Configuração do Cliente (`clients/demo_mercado_livre.json`)

```jsonc
{
  "client_id": "demo_mercado_livre",        // identificador único
  "nome_escritorio": "Demo - Mercado Livre",
  "use_ai_classifier": true,                 // habilitar IA para classificação

  "advogados": [
    {
      "nome": "Bot ML",
      "usuario": null,
      "senha_ref": "VAULT:DEMO",
      "certificado_path": null,
      "email_2fa": null
    }
  ],

  "portais_ativos": ["mercado_livre"],

  "emails_destino": ["demo@example.com"],

  // Regras de classificação: palavra-chave → categoria
  "classification_rules": {
    "notebook": "Informática",
    "iphone": "Celulares",
    "tv": "Eletrônicos"
  }
}
```

### 3. Prioridade de Credenciais

```
1. Windows Credential Manager  (keyring → target="rpa_core", username=<senha_ref>)
2. Variáveis de Ambiente       (.env → <senha_ref>)
3. Erro                        (KeyError — execução interrompida)
```

---

## 🖥️ Uso

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Dry-run (validar configuração sem executar)
python -m src.main --client-id demo_mercado_livre --dry-run

# Execução headless (padrão)
python -m src.main --client-id demo_mercado_livre

# Com navegador visível (debug)
python -m src.main --client-id demo_mercado_livre --no-headless

# Usando Selenium Grid remoto
python -m src.main --client-id demo_mercado_livre --remote-selenium http://localhost:4444

# Listar clientes disponíveis
python -m src.main --list-clients

# Via variável de ambiente
CLIENT_ID=demo_mercado_livre python -m src.main
```

### Dry-run

O modo `--dry-run` valida a configuração e o carregamento dos plugins sem executar scraping:

```bash
python -m src.main --client-id demo_mercado_livre --dry-run
# ✓ DRY RUN — demo_mercado_livre: configuration OK
```

### Saída esperada (execução completa)

```
17:06:19 | INFO | main | Autobot RPA starting — client=demo_mercado_livre
17:06:20 | INFO | orchestrator | Pipeline started | lawyers=1 | platforms=1
17:06:21 | INFO | orchestrator | → Bot ML | mercado_livre | authenticating …
17:06:22 | INFO | mercado_livre | ✅ Autenticado com sucesso.
17:06:23 | INFO | orchestrator | → Bot ML | mercado_livre | fetched 10 raw records
17:06:24 | INFO | orchestrator | Pipeline finished | records=10 | elapsed=2.1s
17:06:24 | INFO | main | ✓ Done — data/output/demo_mercado_livre/records_2026-07-06.xlsx
```

---

## 🔌 Criando um Novo Plugin

Para adicionar uma nova plataforma (ex: Amazon, Buscapé, etc.):

### Passo 1 — Criar a classe

```python
# src/plugins/minha_plataforma/plugin.py
from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType

class MinhaPlataformaPlugin(PortalPlugin):

    @property
    def portal_type(self) -> PortalType:
        return PortalType.MERCADO_LIVRE  # ou adicione um novo no enum

    @property
    def portal_name(self) -> str:
        return "Minha Plataforma"

    def __init__(self, headless: bool = True, remote_url: str | None = None):
        self.headless = headless
        self.remote_url = remote_url

    async def authenticate(self, advogado, config) -> bool:
        ...

    async def fetch_intimations(self, advogado, data_ref) -> list[dict]:
        ...

    async def process_intimation(self, raw, advogado) -> IntimacaoRecord:
        ...

    async def take_action(self, record, advogado) -> None:
        ...

    async def cleanup(self) -> None:
        ...
```

### Passo 2 — Registrar no orquestrador

```python
# src/orchestrator.py — adicione ao PLUGIN_REGISTRY
PLUGIN_REGISTRY[PortalType.MINHA_PLATAFORMA] = "src.plugins.minha_plataforma.plugin.MinhaPlataformaPlugin"
```

### Passo 3 — Adicionar ao enum

```python
# src/models.py
class PortalType(str, Enum):
    MERCADO_LIVRE = "mercado_livre"
    GOOGLE_MAPS = "google_maps"
    RECLAME_AQUI = "reclame_aqui"
    MINHA_PLATAFORMA = "minha_plataforma"  # novo
```

### Passo 4 — Ativar na config do cliente

```json
{
  "portais_ativos": ["mercado_livre", "minha_plataforma"]
}
```

### Regras para plugins

| Regra | Detalhe |
|---|---|
| **Waits explícitos** | `WebDriverWait` com timeout 30s. **Nunca** `time.sleep()` |
| **Selectors robustos** | Prefira `By.XPATH` ou `By.CSS_SELECTOR` |
| **Headless** | Use `self.headless` — nunca hardcode |
| **2FA** | Use `Email2FAHandler.wait_for_code()` |
| **Erro → screenshot** | `base_selenium_plugin` já salva em `data/logs/` |
| **Retry** | Use o decorator `@retry_on_transient` do `base_selenium_plugin` |

---

## 🧠 Classificação (De-Para)

O `HybridClassifier` opera em 3 estágios:

```
1. REGEX (custo zero)
   ├─ Itera as classification_rules do JSON
   ├─ keyword in texto.lower() → match exato
   └─ Confiança: 1.0

2. LLM (opcional, se use_ai_classifier=true)
   ├─ Envia prompt com lista de categorias
   ├─ Valida que resposta é uma categoria conhecida
   └─ Confiança: ai_fallback_threshold (default 0.8)

3. FALLBACK
   └─ Retorna "CLASSIFICACAO_MANUAL" / 0.0
      O analista revisa depois na planilha
```

### Provedores LLM suportados

| Prioridade | Provedor | Variável |
|---|---|---|
| 1 | **DeepSeek** | `LLM_API_KEY` |
| 2 | Azure OpenAI | `AZURE_OPENAI_API_KEY` |
| 3 | OpenAI | `OPENAI_API_KEY` |

Se nenhuma chave for configurada → classificação somente por regex (sem IA).

---

## 🔐 Segurança

### Credential Vault

```
┌──────────────────────────────┐
│ 1. Windows Credential Manager │  ← keyring (produção)
│    target: "rpa_core"         │
│    username: <senha_ref>      │
├──────────────────────────────┤
│ 2. Environment Variables      │  ← .env (dev/fallback)
│    <senha_ref>=<valor>        │
├──────────────────────────────┤
│ 3. KeyError                   │  ← execução interrompida
└──────────────────────────────┘
```

### Certificados Digitais

```python
from src.security.certificate_handler import CertificateHandler

cert = CertificateHandler.load(
    "certs/advogado.pfx",
    password_ref="VAULT:CERT_PASSWORD"
)
```

---

## 🐳 Docker

### Subir Selenium Grid + Rodar RPA

```bash
# 1. Iniciar o Grid
docker compose up -d selenium-hub chrome-node

# 2. Rodar o RPA (one-shot)
docker compose run --rm rpa --client-id demo_mercado_livre

# 3. Ou tudo junto
CLIENT_ID=demo_mercado_livre docker compose up

# 4. Parar tudo
docker compose down
```

### Serviços no `docker-compose.yml`

| Serviço | Porta | Descrição |
|---|---|---|
| `selenium-hub` | 4444 | Selenium Grid Hub |
| `chrome-node` | 5900 | Chrome + VNC (debug visual) |
| `rpa` | — | App Python (executa e sai) |

---

## 🧪 Testes

```bash
# Todos os testes
pytest

# Apenas modelos
pytest tests/test_models.py -v

# Apenas classificador
pytest tests/test_classifier.py -v

# Com coverage
pytest --cov=src --cov-report=term-missing
```

---

## 📊 Logs & Debug

### Formato

Logs usam **JSON lines** para ingestão em ELK / Splunk / Datadog:

```json
{"ts": "2026-07-06T20:06:19.123Z", "level": "INFO", "logger": "orchestrator",
 "msg": "Pipeline finished | records=10 | elapsed=2.1s | output=data/output/..."}
```

### Localização

| Artefato | Caminho |
|---|---|
| Logs diários | `data/logs/execution_YYYY-MM-DD.log` |
| Screenshots de erro | `data/logs/screenshot_error_YYYYMMDD_HHMMSS.png` |
| Planilhas | `data/output/<client_id>/records_YYYY-MM-DD.xlsx` |

### Rotação

- **Tamanho máximo:** 10 MiB por arquivo
- **Backups:** 30 arquivos mantidos
- **Console:** nível INFO (stderr, formato legível)
- **Arquivo:** nível DEBUG (JSON)

---

## 📄 Licença

MIT — veja o arquivo [LICENSE](LICENSE) (se disponível).

---

**Feito com ☕ e Python. 100% genérico, 0% hardcoded.**
