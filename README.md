# Qualital Nexus

Plataforma interna da Qualital para autenticação, acesso às ferramentas corporativas e conversão de documentos técnicos em uma matriz estruturada.

## Visão geral

- Frontend: Next.js 15, React 19 e TypeScript.
- Autenticação e dados: Supabase Auth e Postgres com RLS.
- Backend: FastAPI e Python 3.12.
- IA: Ollama no desenvolvimento ou OpenRouter em produção.
- Entrada: arquivos PDF, DOC e DOCX.
- Saída: XLSX por padrão ou CSV.

O fluxo completo está descrito em [docs/architecture.md](docs/architecture.md).

## Início rápido

### Frontend

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

Preencha em `.env.local`:

```env
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

O frontend estará disponível em `http://localhost:3000`.

### Backend

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Valide em `http://localhost:8000/health`. A documentação OpenAPI gerada pelo FastAPI fica em `http://localhost:8000/docs`.

## Rotas da aplicação

| Rota | Finalidade |
|---|---|
| `/login` | Autenticação por e-mail e senha no Supabase. |
| `/dashboard` | Catálogo das ferramentas disponíveis. |
| `/ferramentas/extracao-pdf` | Envio, ordenação, processamento e download dos documentos. |

## Documentação

| Documento | Conteúdo |
|---|---|
| [Arquitetura](docs/architecture.md) | Componentes, integrações e fluxo ponta a ponta. |
| [Frontend](docs/frontend.md) | Rotas, componentes, autenticação e como adicionar ferramentas. |
| [Backend](docs/backend.md) | Pipeline ativo, módulos, configuração e testes. |
| [API](docs/api.md) | Endpoints, parâmetros, headers, respostas e erros. |
| [Supabase](docs/supabase.md) | Tabelas, RLS, funções, chaves e limitações atuais. |
| [Deploy](docs/deployment.md) | Vercel, Caddy e Hostinger com Traefik. |
| [Troubleshooting](docs/troubleshooting.md) | Diagnóstico dos erros mais comuns. |
| [Regras do parser](backend/supabase/README.md) | Precedência e manutenção de `parser_rules`. |

## Validação

```powershell
npm run build
Push-Location backend
.venv\Scripts\python.exe -m compileall -q app tests
.venv\Scripts\python.exe -m unittest discover -s tests -q
Pop-Location
```

O frontend ainda não possui scripts de lint ou testes automatizados. Consulte as limitações registradas em [docs/frontend.md](docs/frontend.md#limitações-atuais).

## Segurança

- Nunca coloque `SUPABASE_SERVICE_ROLE_KEY`, chaves secretas do Supabase ou `OPENROUTER_API_KEY` em variáveis `NEXT_PUBLIC_*`.
- Arquivos `.env` não devem ser versionados.
- O frontend exige sessão nas telas internas e as rotas FastAPI validam o Bearer token no Supabase. `AUTH_REQUIRED` é `true` por padrão; consulte [docs/backend.md](docs/backend.md#autenticação-da-api).


