# Frontend

## Stack e execução

O frontend usa Next.js com App Router, React e TypeScript. Os estilos estão centralizados em `src/app/globals.css`.

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

## Variáveis de ambiente

| Variável | Obrigatória | Uso |
|---|---:|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Sim | URL do projeto Supabase, sem necessidade do sufixo `/rest/v1`. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Sim | Chave pública/anon usada pelo navegador para Auth e Data API com RLS. |
| `NEXT_PUBLIC_API_URL` | Sim, salvo override | Base da API; o serviço acrescenta `/api/extracao-pdf/process`. |
| `NEXT_PUBLIC_EXTRACAO_PDF_API_URL` | Não | URL completa do endpoint de processamento; tem precedência sobre `NEXT_PUBLIC_API_URL`. |

Variáveis `NEXT_PUBLIC_*` são incluídas no bundle do navegador. Nunca use nelas service role, secret key ou chave do OpenRouter.

## Rotas

| Rota | Implementação | Comportamento |
|---|---|---|
| `/` | `src/app/page.tsx` | Redireciona para `/login`. |
| `/login` | `src/app/login/page.tsx` | Login por e-mail e senha; redireciona uma sessão existente para o dashboard. |
| `/dashboard` | `src/app/dashboard/page.tsx` | Exibe o perfil e as ferramentas registradas. |
| `/ferramentas/extracao-pdf` | `src/app/ferramentas/extracao-pdf/page.tsx` | Gerencia fila, modo de tabela, progresso e download. |

`/dashboard` e `/ferramentas/extracao-pdf` são envolvidos por `AuthGuard`. Essa proteção é de interface; ela não substitui a autenticação no backend.

## Autenticação e perfil

1. `getSupabaseBrowserClient` cria e reutiliza um cliente no navegador.
2. O login usa `signInWithPassword`.
3. `AuthGuard` consulta `getSession` e acompanha `onAuthStateChange`.
4. `useAuthenticatedProfile` confirma o usuário com `getUser` e lê `public.profiles` pelo ID autenticado.
5. `AppHeader` encerra a sessão com `signOut`.

Se o perfil não existir, o frontend continua com o e-mail do usuário e apresenta um aviso. A leitura de `profiles` depende da política RLS descrita em [supabase.md](supabase.md).

## Extração de documentos

### Fila

- Extensões aceitas na interface: PDF, DOC e DOCX.
- A ordem da fila define a ordem dos `append` no `FormData` e deve ser preservada.
- É possível adicionar, remover e reordenar arquivos antes do envio.
- Quantidade e tamanho são validados definitivamente pelo backend.

### Modos de tabela

- `imagem`: preserva tabelas como imagens quando o extrator considera necessário.
- `texto`: serializa as tabelas para processamento textual.

O modo é enviado no parâmetro `table_mode`.

### Progresso

Quando `onProgress` é fornecido, o cliente:

1. gera um UUID;
2. envia-o no header `X-Processing-Id`;
3. consulta `GET /process/{id}/status` a cada 1,25 segundo;
4. encerra o polling quando a requisição principal termina.

O token de sessão, quando disponível, é enviado como `Authorization: Bearer <JWT>` nas duas requisições.

### Download

A resposta é convertida em `Blob`, exposta temporariamente por `URL.createObjectURL` e baixada usando o nome de `Content-Disposition`. A URL anterior é revogada ao substituir ou desmontar o resultado.

## Organização do código

| Diretório | Responsabilidade |
|---|---|
| `src/app` | Rotas e layout. |
| `src/components` | Componentes reutilizáveis de interface. |
| `src/hooks` | Leitura do perfil autenticado. |
| `src/lib` | Cliente Supabase, catálogo de ferramentas e validação de extensão. |
| `src/services` | Comunicação com a API e mock legado. |
| `src/types` | Contratos TypeScript. |

`extracaoPdfService.ts` resolve a URL configurada e delega a chamada para `extracaoPdfApiService.ts`. `extracaoPdfMockService.ts` não participa do fluxo real.

## Adicionar uma ferramenta

1. Crie a rota em `src/app/ferramentas/<slug>/page.tsx`.
2. Adicione o item em `src/lib/tools.ts`.
3. Reutilize `AuthGuard` e `AppHeader` quando a ferramenta exigir sessão.
4. Crie contratos em `src/types` e isole a integração HTTP em `src/services`.
5. Inclua nome acessível para ícones e preserve operação por teclado.
6. Execute `npm run build`.

O campo `acessoMinimo` já existe no catálogo, mas atualmente não filtra nem bloqueia ferramentas por cargo.

## Limitações atuais

- Não há scripts de lint ou testes no `package.json`.
- Não existe middleware de proteção no servidor Next.js; a verificação ocorre no cliente.
- O limite de quantidade e tamanho aparece somente após resposta do backend.
- O mock de extração é código legado e não deve ser usado como substituto silencioso da API.
- O acesso mínimo registrado nas ferramentas ainda não é aplicado.
- A descrição da ferramenta no dashboard ainda menciona CSV, embora a saída padrão atual seja XLSX.
