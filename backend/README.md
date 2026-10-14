# Backend local — Qualital Nexus

API FastAPI da ferramenta **Extração de documentos**. Recebe arquivos PDF, DOC e DOCX em `multipart/form-data`, preserva a ordem das partes, consulta regras do parser no Supabase, transforma cada bloco e devolve `matriz_priorizacao.xlsx` como saída principal e permite CSV compatível com `?format=csv`.

A arquitetura, o pipeline ativo e todas as variáveis estão documentados em [../docs/backend.md](../docs/backend.md). O contrato HTTP completo está em [../docs/api.md](../docs/api.md).

## Configuração

Crie `backend/.env` a partir de `.env.example` (ou use o `.env` da raiz):

```env
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-5-nano
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
AUTH_REQUIRED=false
FRONTEND_ORIGIN=http://localhost:3000
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3:8b
```

`SUPABASE_SERVICE_ROLE_KEY` é exclusiva do backend e nunca deve ser colocada em variáveis `NEXT_PUBLIC_*` nem versionada. Sem Supabase, a API funciona sem regras e exemplos remotos; sem a chave do OpenRouter, use `LLM_PROVIDER=ollama` no desenvolvimento ou a conversão retornará um erro claro.

Para criar, revisar ou substituir regras, consulte [supabase/README.md](supabase/README.md), que documenta campos, precedência e auditoria da tabela `parser_rules`.

## Executar localmente

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Teste a saúde do serviço em `GET http://localhost:8000/health`.

Abra `http://localhost:8000/docs` para consultar o Swagger gerado pelo FastAPI.

Para o frontend, defina `NEXT_PUBLIC_API_URL=http://localhost:8000`. O cliente envia cada documento como `files[]`, na mesma ordem exibida na tela. A API também aceita o campo legado `files`.

## Endpoints

- `POST /api/extracao-pdf/process`: devolve `matriz_priorizacao.xlsx` como download por padrão; use `?format=csv` para CSV.
- `GET /api/extracao-pdf/process/{id}/status`: devolve o progresso associado ao header `X-Processing-Id`.
- `POST /api/extracao-pdf/debug`: devolve blocos, categorias, exemplos do parser, regras selecionadas e prévia das linhas.

Os endpoints de processamento aceitam `table_mode=imagem|texto` e um ou mais arquivos PDF, DOC ou DOCX, até 20 arquivos de 25 MB por padrão. PDFs sem camada de texto ainda não têm OCR.

O frontend envia o JWT do Supabase e todas as rotas de extração validam esse token. `AUTH_REQUIRED` é `true` por padrão; use `false` somente no desenvolvimento local sem Supabase.

## Testes

```powershell
.venv\Scripts\python.exe -m compileall -q app tests
.venv\Scripts\python.exe -m unittest discover -s tests -q
```

## Deploy

Há dois modos distintos: Caddy próprio com `docker-compose.yml` ou Traefik existente com `docker-compose.hostinger.yml`. Consulte [../docs/deployment.md](../docs/deployment.md) e não misture os dois no mesmo ambiente.
