# Backend local — Qualital Nexus

API FastAPI da ferramenta **Extração de documentos**. Recebe arquivos PDF, DOC e DOCX em `multipart/form-data`, preserva a ordem das partes, consulta regras e exemplos no Supabase, transforma cada bloco e devolve `matriz_priorizacao.xlsx` como saída principal e permite CSV compatível com `?format=csv`.

## Configuração

Crie `backend/.env` a partir de `.env.example` (ou use o `.env` da raiz):

```env
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-5-nano
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
FRONTEND_ORIGIN=http://localhost:3000
```

`SUPABASE_SERVICE_ROLE_KEY` é exclusiva do backend e nunca deve ser colocada em variáveis `NEXT_PUBLIC_*` nem versionada. Sem Supabase, a API funciona sem regras e exemplos remotos; sem a chave do OpenRouter, use `LLM_PROVIDER=ollama` no desenvolvimento ou a conversão retornará um erro claro.

## Executar localmente

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Teste a saúde do serviço em `GET http://localhost:8000/health`.

Para o frontend, defina `NEXT_PUBLIC_API_URL=http://localhost:8000`. O cliente envia cada documento como `files[]`, na mesma ordem exibida na tela. A API também aceita o campo legado `files`.

## Endpoints

- `POST /api/extracao-pdf/process`: devolve `matriz_priorizacao.xlsx` como download por padrão; use `?format=csv` para CSV.
- `POST /api/extracao-pdf/debug`: devolve blocos, categorias, contagem de exemplos RAG, regras selecionadas e prévia das linhas.

Ambos aceitam um ou mais arquivos PDF, DOC ou DOCX, até 20 arquivos de 25 MB por padrão. PDFs sem camada de texto ainda não têm OCR.

## Deploy na Hostinger VPS

A API pode ser executada na VPS com Docker e Caddy. No diretório do projeto:

```bash
cp backend/.env.example backend/.env
# Edite backend/.env e defina SUPABASE_SERVICE_ROLE_KEY,
# OPENROUTER_API_KEY, OPENROUTER_MODEL e FRONTEND_ORIGIN.
# No .env da raiz, defina API_DOMAIN=api.seudominio.com.
docker compose up -d --build
curl https://api.seudominio.com/health
```

Abra as portas TCP 80 e 443 no firewall da VPS. O Caddy provisiona e renova o certificado TLS automaticamente. No Vercel, defina `NEXT_PUBLIC_API_URL=https://api.seudominio.com`.

Para desenvolvimento local, mantenha `LLM_PROVIDER=ollama`. Para produção, use `LLM_PROVIDER=openrouter`; a chave do OpenRouter e a `SUPABASE_SERVICE_ROLE_KEY` ficam somente em `backend/.env` e nunca devem ser versionadas.
