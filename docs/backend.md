# Backend

## Stack e execução

O backend usa FastAPI, Pydantic, PyMuPDF, python-docx, olefile, httpx e o cliente Python do Supabase.

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Saúde: `GET http://localhost:8000/health`.
- Swagger: `http://localhost:8000/docs`.
- OpenAPI JSON: `http://localhost:8000/openapi.json`.

## Configuração

| Variável | Padrão | Uso |
|---|---|---|
| `ENVIRONMENT` | `development` | Nome do ambiente nos logs. |
| `LOG_LEVEL` | `INFO` | Nível do logging Python/Uvicorn. |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | Origens CORS separadas por vírgula. Também aceita o alias `CORS_ORIGINS`. |
| `MAX_FILES` | `20` | Máximo de arquivos por requisição. |
| `MAX_FILE_SIZE_MB` | `25` | Tamanho máximo individual. |
| `SUPABASE_URL` | vazio | URL do projeto. |
| `SUPABASE_SERVICE_ROLE_KEY` | vazio | Chave privilegiada usada somente pelo backend. |
| `SUPABASE_ANON_KEY` | vazio | Chave pública usada pela função de validação de sessão. |
| `AUTH_REQUIRED` | `true` | Exige configuração de Auth; use `false` somente no desenvolvimento local sem Supabase. |
| `LLM_PROVIDER` | `ollama` | `ollama` ou `openrouter`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Endpoint compatível com OpenAI. |
| `OLLAMA_MODEL` | `qwen3:8b` | Modelo local. |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | Timeout HTTP do Ollama. |
| `OLLAMA_MAX_REQUEST_SECONDS` | `90` | Limite interno por tentativa. |
| `OLLAMA_MAX_RESPONSE_CHARACTERS` | `24000` | Limite de resposta acumulada. |
| `OPENROUTER_API_KEY` | vazio | Segredo do OpenRouter. |
| `OPENROUTER_MODEL` | `openai/gpt-5-nano` | Modelo remoto. |
| `OPENROUTER_HTTP_REFERER` | vazio | Referer opcional do OpenRouter. |
| `OPENROUTER_APP_TITLE` | vazio | Título opcional enviado ao OpenRouter. |
| `EXTRACTION_BATCH_MAX_CHARS` | `40000` | Teto configurável; o router também limita cada lote a 12000 caracteres. |

As configurações são lidas primeiro de `backend/.env` e também podem vir do `.env` da raiz. Não versione esses arquivos.

## Pipeline ativo

O fluxo chamado por `/api/extracao-pdf/process` é:

1. `routers/extracao_pdf.py`: valida HTTP, aplica autenticação e produz a resposta.
2. `extraction_pipeline_service.py`: orquestra o caso de uso e recebe o repositório de regras e o conversor LLM por contrato.
3. `document_service.py`: identifica PDF/DOC/DOCX e extrai conteúdo.
4. `pdf_service.py`: limpa texto, detecta tabelas/imagens, separa blocos, categorias e escopos.
5. `parser_rules_service.py`: carrega regras ativas do Supabase e escolhe regras compatíveis.
6. `llm_service.py`: monta o prompt, chama Ollama/OpenRouter, valida cobertura e aplica fallbacks.
7. `matrix_structure_service.py`: consolida a hierarquia das tarefas e anexos.
8. `normalizer_service.py`: normaliza as colunas finais.
9. `xlsx_service.py` ou `csv_service.py`: gera o arquivo retornado.
10. `processing_status.py`: mantém o progresso em memória por até uma hora.

As imagens não são enviadas como blocos textuais ao LLM. Quando preservadas, tornam-se linhas informativas incorporadas no XLSX.

## Regras e conflitos

As regras do parser vêm de `public.parser_rules`. A seleção considera regex ou fallback categórico, categoria, data de atualização e ordem. Consulte [../backend/supabase/README.md](../backend/supabase/README.md).

Se o Supabase não estiver configurado ou a consulta falhar, o processamento continua sem regras remotas e registra a falha no log.

## Falhas parciais

Cada arquivo é dividido em lotes de até oito blocos e no máximo 12000 caracteres. Uma falha de conversão em um lote não cancela automaticamente os demais: o lote é registrado em `falhas_lotes` e a API pode devolver `matriz_priorizacao_parcial.*`.

O cliente deve conferir `X-Extraction-Partial` e `X-Extraction-Failures`.

## Autenticação da API

Todas as rotas de extração aplicam `require_authenticated_user`. Com `SUPABASE_URL` e `SUPABASE_ANON_KEY`, o Bearer token é obrigatório e validado no endpoint oficial de Auth. Sem essas credenciais, o acesso local só é permitido quando `AUTH_REQUIRED=false`; em produção, configure `AUTH_REQUIRED=true` para falhar com 503 em vez de iniciar sem proteção.

## CORS

O backend aceita `GET` e `POST`, credenciais e os headers `Authorization`, `Content-Type` e `X-Processing-Id` para as origens configuradas em `FRONTEND_ORIGIN`.

## Testes

```powershell
cd backend
.venv\Scripts\python.exe -m compileall -q app tests
.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Para executar apenas os testes de autenticação:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_security -q
```

## Observabilidade

- Os logs usam o nível definido em `LOG_LEVEL`.
- Pollings de status bem-sucedidos são omitidos do access log para reduzir ruído.
- Falhas de lotes incluem arquivo, ordem do lote e ordens dos blocos.
- Não há persistência de jobs, métricas ou tracing distribuído.

