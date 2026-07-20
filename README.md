# Qualital Nexus

Plataforma interna da Qualital para acessar ferramentas corporativas, com foco inicial em autenticação, dashboard e Extração PDF.

## Stack

- Next.js com App Router
- TypeScript
- Supabase Auth no frontend
- CSS moderno e responsivo

## Como rodar

1. Copie `.env.example` para `.env.local`.
2. Preencha `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
3. Instale as dependências com `npm install`.
4. Execute `npm run dev`.

## Rotas principais

- `/login`
- `/dashboard`
- `/ferramentas/extracao-pdf`

## Estrutura inicial

- Lista de ferramentas local em `src/lib/tools.ts`
- Proteção de páginas com `src/components/AuthGuard.tsx`
- Serviço isolado da extração em `src/services/extracaoPdfService.ts`
- Tipos em `src/types`
