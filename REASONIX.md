# REASONIX.md - Contexto e Regras de Engenharia

## 1. VISÃO GERAL DO PROJETO
Este é um **RPA (Robotic Process Automation) Genérico e Multi-Tenant** para extração de dados em múltiplas plataformas web (Mercado Livre, Google Maps, Reclame Aqui, etc.).
- **Linguagem:** Python 3.10+
- **Paradigma:** Programação Orientada a Objetos (POO) + Programação Assíncrona (asyncio)
- **Arquitetura:** Hexagonal (Ports & Adapters) para permitir plugabilidade de novas plataformas sem alterar o core.
- **Saída:** Planilha Excel unificada enviada por e-mail.
- **Público-alvo:** Múltiplos clientes (multi-tenant).

## 2. PRINCÍPIOS FUNDAMENTAIS (NÃO NEGOCIÁVEIS)
1. **100% Genérico:** Nenhum nome de cliente, escritório ou plataforma específica deve estar hardcoded no código fonte. Tudo vem de configuração (JSON/Env).
2. **Multi-Tenant:** Um único código base deve atender múltiplos clientes simultaneamente, diferenciados pelo `client_id`.
3. **Sem GUI:** O sistema é headless (roda em terminal/serviço). Nenhuma interface gráfica (Tkinter, PyQt) é permitida.
4. **Config-Driven:** Todo comportamento (plataformas ativas, usuários, regras de classificação, e-mails) deve ser definido em arquivos JSON externos.
5. **IA como Aprimoramento, não como Dependência:** A IA (LLM) é usada APENAS para classificação de textos (De-para) quando o Regex falha. Se a API de IA falhar, o sistema deve fazer fallback para "CLASSIFICACAO_MANUAL" sem quebrar.

## 3. ARQUITETURA TÉCNICA (A ESTRUTURA QUE VOCÊ DEVE SEGUIR)

### 3.1. Estrutura de Pastas (Obrigatória)
```
autobot-rpa/
├── src/
│   ├── main.py                  # Entrypoint: parse de argumentos (--client-id, --headless, --dry-run)
│   ├── orchestrator.py          # Orquestrador principal (dispara a pipeline)
│   ├── config_manager.py        # Carrega JSONs da pasta clients/
│   ├── models.py                # Pydantic models (IntimacaoRecord, ClienteConfig, etc.)
│   ├── interfaces/              # ABCs (contratos)
│   │   ├── portal_plugin.py     # Classe abstrata para plugins de plataforma
│   │   ├── scraper.py           # Classe abstrata para scrapers (search/extract)
│   │   ├── classifier.py        # Classe abstrata para classificadores
│   │   └── output_writer.py     # Classe abstrata para escrita
│   ├── plugins/                 # Implementações concretas de plataformas
│   │   ├── base_selenium_plugin.py  # Helper com waits e setup do driver
│   │   ├── mercado_livre/           # Plugin Mercado Livre
│   │   ├── google_maps/             # Plugin Google Maps
│   │   └── reclame_aqui/            # Plugin Reclame Aqui
│   ├── services/                # Lógica de negócio
│   │   ├── classifier_service.py    # Híbrido (Regex + IA)
│   │   ├── llm_client.py            # LangChain + OpenAI/Azure
│   │   └── excel_writer.py          # Pandas/OpenPyXL
│   ├── security/                # Segurança e credenciais
│   │   ├── credential_vault.py  # Leitura de secrets (Windows CredMan / .env)
│   │   └── certificate_handler.py # Carregamento de certificados .pfx
│   └── utils/                   # Utilitários transversais
│       ├── logger.py            # Logging estruturado (JSON lines)
│       └── email_2fa_handler.py # IMAP para capturar códigos de verificação
├── clients/                     # Configurações dos clientes (JSON)
│   ├── demo_mercado_livre.json
│   ├── demo_google_maps.json
│   └── demo_reclame_aqui.json
├── data/
│   ├── output/                  # Planilhas geradas (organizadas por client_id/data)
│   └── logs/                    # Logs de execução (execution_YYYY-MM-DD.log)
├── tests/                       # Testes unitários (pytest)
│   ├── test_models.py
│   └── test_classifier.py
├── .env                         # Variáveis de ambiente (OPENAI_API_KEY, EMAIL_PASSWORD)
├── requirements.txt             # Dependências (selenium, pandas, langchain, etc.)
├── docker-compose.yml           # Para execução headless com Selenium Grid (opcional)
└── REASONIX.md                  # Este arquivo
```

### 3.2. Fluxo de Execução (Pipeline)
1. **Inicialização:** `main.py` lê o argumento `--client-id` e carrega o JSON correspondente.
2. **Orquestração:** `orchestrator.py` itera sobre os advogados e portais ativos.
3. **Autenticação:** O plugin do portal executa login, 2FA (se necessário) e carrega certificados.
4. **Extração (Fetch):** O plugin retorna dados brutos (listas de dicionários).
5. **Transformação (Process):** Os dados brutos são mapeados para `IntimacaoRecord`.
6. **Classificação (Classify):** O `HybridClassifier` aplica Regex e, se configurado, LLM.
7. **Ação (Action):** O plugin executa ações específicas (ex: "Tomar Ciência" ou "Ignorar").
8. **Persistência:** `ExcelWriter` gera a planilha unificada.
9. **Notificação:** Envia e-mail com a planilha anexada (usando `smtplib`).

## 4. REGRAS DE IMPLEMENTAÇÃO PARA O AGENTE

### 4.1. Para criAR um NOVO PORTAL (Plugin)
- **Herança:** Deve herdar de `src.interfaces.portal_plugin.PortalPlugin`.
- **Registro:** Deve ser adicionado ao `PLUGIN_REGISTRY` no `orchestrator.py` (ou arquivo de factory).
- **Selectors:** Use `WebDriverWait` com timeout de 30 segundos. Prefira `By.XPATH` ou `By.CSS_SELECTOR` robustos. Nunca use `time.sleep()` fixo; use waits explícitos (presence_of_element_located, element_to_be_clickable).
- **2FA:** Se o portal exigir, utilize o `Email2FAHandler` para capturar o código via IMAP (polling a cada 3 segundos, conforme lógica do PDD original).
- **Headless:** O driver deve aceitar a flag `--headless` quando passada via argumento.

### 4.2. Para o CLASSIFICADOR (De-para)
- **Ordem:** Regex primeiro (custo zero), LLM segundo (se habilitado e se Regex falhar).
- **Prompt da IA:** Deve ser curto, restrito a uma lista de categorias fornecidas pelo JSON do cliente, e pedir APENAS a resposta (sem explicações).
- **Fallback:** Se qualquer etapa da IA falhar (timeout, chave inválida), o sistema deve retornar `("CLASSIFICACAO_MANUAL", 0.0)` e registrar o erro no log.

### 4.3. Para o EXCEL (Saída)
- **Ferramenta:** Use `pandas` com `openpyxl` como engine.
- **Estrutura:** A planilha deve conter APENAS as colunas mapeadas no modelo `IntimacaoRecord` (Data, Portal, Advogado, Processo, Destinatario, Status, etc.).
- **Salvamento:** Salvar em `data/output/{client_id}/intimacoes_{data}.xlsx`. Se o diretório não existir, criá-lo.

### 4.4. Para LOGS
- **Formato:** Use `logging` com `JSONFormatter` para facilitar a ingestão por ferramentas como ELK ou Splunk.
- **Níveis:** `INFO` para ações normais (login, início de portal, fim de execução), `ERROR` para exceções, `DEBUG` para detalhes de elementos HTML (útil para troubleshooting).
- **Separação:** Logs devem ser salvos em `data/logs/execution_{data}.log`.

### 4.5. Para SEGURANÇA (Credenciais)
- **Senhas:** NUNCA hardcode. Leia do `CredentialVault`. O Vault deve tentar primeiro o Windows Credential Manager (via `keyring`), depois variáveis de ambiente (`.env`).
- **Certificados:** Carregar via `certificate_handler` usando `ssl` ou `requests` conforme necessidade. Para Selenium, o carregamento é feito via interface do navegador (cliques na extensão ou configuração de perfil).

## 5. TRATAMENTO DE ERROS E RESILIÊNCIA
- **Retry Pattern:** Para falhas de rede ou timeouts, implemente retry com exponential backoff (usando a biblioteca `tenacity`).
- **Exceções Fatais:** Se a autenticação em um portal falhar, registre o erro e PULE para o próximo portal (não derrube a execução inteira).
- **Evidências:** Em caso de erro crítico, tire um screenshot da tela (usando `driver.save_screenshot()`) e salve na pasta `data/logs/` com o timestamp.

## 6. TESTES (Obrigatório para o Agente)
- **Unitários:** Testar os modelos (Pydantic) e o classificador híbrido em modo offline (mockando a LLM).
- **Mocks:** Para testes, simule respostas da LLM e dados de portais. Não dependa de rede externa nos testes unitários.

## 7. RESTRIÇÕES DE DEPENDÊNCIAS
- Use **Selenium** para web scraping (não use Playwright ou Puppeteer, a menos que autorizado).
- Use **LangChain** apenas para integração com LLMs (OpenAI, Azure).
- Use **Pandas** para Excel (é mais rápido e seguro que OpenPyXL puro para DataFrames).
- Versionamento: Python 3.10+, Selenium 4.15+, LangChain 0.1+.

## 8. EXEMPLO DE COMANDO PARA RODAR
```bash
# Instalar dependências
pip install -r requirements.txt

# Executar para um cliente específico (modo debug com navegador visível)
python src/main.py --client-id cliente_alfa

# Executar headless (produção)
python src/main.py --client-id cliente_alfa --headless
```

## 9. ADIÇÃO DE NOVO CLIENTE (Multi-Tenant)
Para adicionar um novo escritório, basta:
1. Criar um arquivo JSON em `src/configs/novo_cliente.json`.
2. Preencher com os advogados, portais ativos, regras de classificação e e-mails.
3. Nenhuma alteração no código é necessária.

## 10. O QUE NÃO FAZER (Anti-Patterns)
- ❌ Não usar `time.sleep()` para esperar elementos (use WebDriverWait).
- ❌ Não misturar lógica de UI com lógica de negócio (mantenha separado nos plugins).
- ❌ Não armazenar credenciais em variáveis globais.
- ❌ Não tratar exceções com `except Exception: pass` (sempre logue o erro).
- ❌ Não modificar o `orchestrator.py` para adicionar um portal novo; use o plugin registry.

---
**Instrução Final para o Agente:** Ao gerar código, siga estritamente esta estrutura de pastas e regras. Priorize a legibilidade, type hints (Pydantic/typing) e docstrings em todas as funções públicas. O objetivo é um sistema "plug-and-play" onde novos portais são adicionados como plugins isolados.
