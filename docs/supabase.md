# Supabase

## Uso no sistema

O Supabase fornece:

- autenticação por e-mail e senha;
- perfil exibido no frontend;
- regras configuráveis do parser.

O frontend usa uma chave pública/anon e depende de RLS. O backend usa `SUPABASE_SERVICE_ROLE_KEY`, que é privilegiada e não deve chegar ao navegador, logs ou repositório.

## Tabelas atuais

Todas as tabelas abaixo estão no schema `public` e possuem RLS habilitada.

### `profiles`

Perfil associado a `auth.users` por `id`.

| Campo | Uso |
|---|---|
| `id` | UUID do usuário e chave primária. |
| `nome`, `username`, `email` | Identificação exibida ou administrativa. |
| `setor` | Setor opcional. |
| `cargo` | `chefe`, `ti`, `analista` ou `usuario`. |
| `avatar_url` | Imagem opcional. |
| `ativo` | Estado do perfil. |
| `created_at`, `updated_at` | Auditoria temporal. |

O frontend lê `id`, `nome`, `email` e `role`, mas o schema atual possui `cargo` e não possui `role`. Essa divergência precisa ser corrigida no código ou no schema antes de depender do cargo no frontend.

### `parser_rules`

Regras ativas consultadas pelo backend para orientar a classificação. A referência completa está em [../backend/supabase/README.md](../backend/supabase/README.md), e a carga de referência está em `backend/supabase/parser_rules_reference.sql`.

Campos principais: `nome`, `descricao`, `ativo`, `ordem`, `escopo`, `padrao_regex`, `tipo_tarefa`, `categoria`, exemplos e timestamps.

## Políticas RLS atuais

| Tabela | Política | Operação | Regra resumida |
|---|---|---|---|
| `profiles` | `profiles_select` | SELECT | Próprio usuário ou TI/chefe. |
| `profiles` | `profiles_update_admin` | UPDATE | TI/chefe. |
| `parser_rules` | `parser_rules_select` | SELECT | Usuário autenticado lê regras ativas. |
| `parser_rules` | `parser_rules_manage` | ALL | TI/chefe. |

O backend com service role não é restringido por RLS. A autorização da API precisa ocorrer antes de qualquer operação privilegiada.

## Funções e gatilhos

Funções de negócio existentes:

- `eh_chefe()`;
- `eh_ti_ou_chefe()`;
- `handle_new_user()`;
- `meu_cargo()`;
- `nivel_cargo(text)`;
- `rls_auto_enable()`;
- `set_updated_at()`.

Gatilhos de `updated_at` existem em `profiles` e `parser_rules`. Em `parser_rules`, o timestamp só muda quando o conteúdo realmente muda.

Algumas funções são `SECURITY DEFINER`. Antes de ampliar acesso ou criar RPCs, revise permissões de `EXECUTE`, `search_path` e validação do usuário. Não use `SECURITY DEFINER` apenas para contornar RLS.

## Chaves

| Contexto | Variável | Pode ser pública? |
|---|---|---:|
| Navegador | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Sim, desde que RLS e grants estejam corretos. |
| Backend, validação de usuário | `SUPABASE_ANON_KEY` | Não precisa ser secreta, mas não use como autorização do servidor. |
| Backend privilegiado | `SUPABASE_SERVICE_ROLE_KEY` | Não. Bypassa RLS. |

Projetos novos podem usar chaves publishable/secret no lugar das chaves legadas anon/service role. Consulte a documentação oficial de [API keys](https://supabase.com/docs/guides/getting-started/api-keys).

## Reproduzir o banco

O repositório ainda não contém migrations completas para `profiles`, funções e políticas. `parser_rules_reference.sql` é uma referência/carga idempotente e não substitui uma migration inicial do schema.

Até que as migrations sejam criadas:

1. trate o projeto remoto como fonte do schema atual;
2. não crie tabelas manualmente sem registrar a alteração;
3. mantenha RLS habilitada em tabelas expostas;
4. confirme grants da Data API, pois tabelas novas podem não ser expostas automaticamente;
5. execute os advisors de segurança e desempenho após mudanças.

## Pendências confirmadas

- O frontend consulta `profiles.role`, mas a coluna atual é `cargo`.
- O helper de autenticação da API não está ligado às rotas.
- Não há migrations completas versionadas.
- Advisors apontam funções privilegiadas que exigem revisão de `EXECUTE` e políticas permissivas de SELECT sobrepostas.

Referências oficiais: [segurança dos dados](https://supabase.com/docs/guides/database/secure-data), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) e [segurança da Data API](https://supabase.com/docs/guides/api/securing-your-api).

