# 🤖 Autobot RPA

> Extração automatizada de dados de múltiplas plataformas web.
> Um código, N clientes, N plataformas.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![Selenium](https://img.shields.io/badge/Selenium-4.15+-green?logo=selenium)
![Pydantic](https://img.shields.io/badge/Pydantic-2.5+-purple)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)
![Tests](https://img.shields.io/badge/Tests-84+-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🎯 O que faz

O **Autobot RPA** extrai dados de plataformas web automaticamente usando **Selenium**,
sem necessidade de APIs oficiais. Cada plataforma é um **plugin** independente.
O comportamento é 100% configurável via **JSON** — zero código por cliente.

### Plataformas Suportadas

| Plugin | Dados extraídos | Status |
|--------|----------------|--------|
| 🛒 **Mercado Livre** | Produtos, preços, frete, vendedor, avaliações | ✅ |
| 🗺️ **Google Maps** | Empresas, endereço, telefone, website, rating | ✅ |
| 📦 **OLX Brasil** | Anúncios, preços, localização, data | ✅ |

---

## 🏗️ Arquitetura

```
src/
├── interfaces/          # Contratos abstratos (ABCs)
│   └── scraper.py       # BaseScraper: search() + extract()
├── plugins/             # Implementações por plataforma
│   ├── base_selenium_plugin.py  # Driver + anti-detecção
│   ├── mercado_livre/
│   ├── google_maps/
│   └── olx/
├── services/            # Classificador IA, Exportação Excel
├── models.py            # Pydantic models
├── orchestrator.py      # Pipeline principal
└── main.py              # CLI entry point
```

### Princípios

- **100% Genérico** — nenhum nome de cliente no código
- **Config-Driven** — comportamento via JSON em `clients/`
- **Plugin Architecture** — cada plataforma é independente
- **Anti-Detecção** — Selenium com stealth (User-Agent, CDP, delays aleatórios)
- **Resiliente** — erro em um plugin não derruba a execução
- **Debugável** — screenshot + HTML salvos em caso de erro

---

## 🚀 Como Rodar

### Pré-requisitos

- Python 3.11+
- Google Chrome instalado
- ChromeDriver (compatível com sua versão do Chrome)

### Instalação

```bash
git clone https://github.com/GustavoGarciaPereira/bot-automation.git
cd bot-automation
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### Uso Básico

```bash
# Lista clientes configurados
python src/main.py --list-clients

# Roda extração para um cliente
python src/main.py --client-id demo_mercado_livre
python src/main.py --client-id demo_google_maps
python src/main.py --client-id demo_olx

# Dry run (valida config sem executar)
python src/main.py --client-id demo_olx --dry-run
```

### Scripts de Validação (dados reais)

```bash
python scripts/test_ml_real.py              # Mercado Livre (headless)
python scripts/test_maps_real.py --visible  # Google Maps
python scripts/test_olx_real.py --visible   # OLX
```

### Docker

```bash
docker compose build
docker compose run bot --client-id demo_mercado_livre
docker compose run bot --client-id demo_olx
docker compose run bot --list-clients
```

### Makefile

```bash
make test        # Roda testes
make run-ml      # Valida ML
make run-maps    # Valida Maps
make run-olx     # Valida OLX
make clean       # Limpa cache e logs
```

---

## ⚙️ Configuração

Cada cliente tem um JSON em `clients/`:

```json
{
  "client_id": "demo_olx",
  "nome_escritorio": "Demo - OLX",
  "advogados": [{"nome": "Bot", "senha_ref": "VAULT:DEMO"}],
  "portais_ativos": ["olx"],
  "settings": {
    "search_terms": ["notebook dell", "iphone 15"],
    "max_results": 15
  }
}
```

Para adicionar um novo cliente, crie um novo JSON em `clients/`.
Nenhuma linha de código precisa ser alterada.

---

## 🧪 Testes

```bash
python -m pytest tests/ -v
```

**84+ testes** cobrindo:
- Parsing de HTML (mockado sem Selenium real)
- Modelos Pydantic (validação de dados)
- Price parsing (formato brasileiro: `R$ 1.200`, `R$ 3.499,90`)
- Localização, data, extração de telefone/website
- Fallbacks de selectors CSS
- Config loading e dry-run

---

## 📁 Estrutura de Output

```
output/
└── {client_id}_{timestamp}.xlsx     # Relatório Excel

data/logs/
├── {plugin}_debug_{ts}.html         # HTML da página (debug)
├── {plugin}_debug_{ts}.png          # Screenshot (debug)
└── {plugin}_items_{ts}/             # Cards individuais (debug)
```

---

## 🗺️ Roadmap

- [x] Plugin Mercado Livre
- [x] Plugin Google Maps
- [x] Plugin OLX Brasil
- [ ] Classificação com IA (LLM)
- [ ] Alertas (email / Telegram)
- [ ] Cross-reference entre plataformas
- [ ] Dashboard web
- [ ] API REST

---

## 📄 Licença

MIT

---

## 👨‍💻 Autor

**Gustavo Garcia Pereira**

- GitHub: [@GustavoGarciaPereira](https://github.com/GustavoGarciaPereira)
