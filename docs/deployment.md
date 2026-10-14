# Deploy

O frontend e a API são publicados separadamente. Existem dois modos suportados para expor a API; escolha somente um por ambiente.

## Frontend na Vercel

Configure no projeto:

```env
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=https://api.seudominio.com
```

Depois do deploy, valide login, dashboard, CORS, upload, polling e download.

## API com Docker e Caddy

O `docker-compose.yml` sobe a API e um Caddy próprio nas portas 80 e 443.

Na raiz:

```env
API_DOMAIN=api.seudominio.com
```

Em `backend/.env`:

```env
ENVIRONMENT=production
FRONTEND_ORIGIN=https://app.seudominio.com
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
AUTH_REQUIRED=true
```

```bash
docker compose up -d --build
docker compose ps
curl https://api.seudominio.com/health
```

Use esse modo quando a máquina não possuir um proxy reverso compartilhado.

## API na Hostinger com Traefik existente

O `docker-compose.hostinger.yml` não sobe Caddy. Ele conecta a API à rede externa `n8n_default` e usa o Traefik já instalado com o n8n.

Pré-requisitos:

1. registro DNS `A` do subdomínio apontando para a VPS;
2. rede Docker `n8n_default` existente;
3. resolver TLS `mytlschallenge` configurado no Traefik;
4. `.env` da raiz com `API_DOMAIN`;
5. `backend/.env` com os segredos e `FRONTEND_ORIGIN` correto.

```bash
docker compose -f docker-compose.hostinger.yml up -d --build
docker compose -f docker-compose.hostinger.yml ps
curl https://api.seudominio.com/health
```

Use esse modo na VPS que já hospeda n8n/Traefik. Não execute simultaneamente o compose com Caddy, pois ambos representam estratégias diferentes de proxy.

## Atualização

```bash
git pull
docker compose -f docker-compose.hostinger.yml up -d --build
docker compose -f docker-compose.hostinger.yml logs --tail=200 api
curl https://api.seudominio.com/health
```

Para Caddy, remova `-f docker-compose.hostinger.yml` dos comandos.

## Checklist

- DNS aponta para a VPS.
- HTTPS válido.
- `FRONTEND_ORIGIN` contém a URL exata do frontend.
- Nenhuma chave privilegiada está no frontend.
- `/health` responde 200.
- Swagger não expõe segredos ou dados reais.
- Login funciona no domínio final.
- Upload, progresso e download foram testados com documento não sensível.
- Reinício do container e logs foram verificados.
- Alterações de banco foram aplicadas e auditadas separadamente; o deploy atual não executa migrations.

