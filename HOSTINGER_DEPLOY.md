# Deploy da API na VPS Hostinger

Este arquivo de deploy publica somente a API FastAPI do Qualital Nexus. Ele usa o Traefik já instalado com o n8n para disponibilizar HTTPS e não altera os containers nem os fluxos do n8n.

## Pré-requisitos

1. Crie o registro DNS `A` do subdomínio `api` apontando para o IP da VPS.
2. Na raiz do projeto na VPS, crie `.env` com `API_DOMAIN=api.seudominio.com`.
3. Crie `backend/.env` a partir de `backend/.env.example` e defina `ENVIRONMENT=production`, `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` e `FRONTEND_ORIGIN`.

## Iniciar

```bash
docker compose -f docker-compose.hostinger.yml up -d --build
```

## Validar

```bash
docker compose -f docker-compose.hostinger.yml ps
curl https://api.seudominio.com/health
```

## Atualizar

```bash
git pull
docker compose -f docker-compose.hostinger.yml up -d --build
```
