# Troubleshooting

## Frontend informa que o Supabase não está configurado

Confirme `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_ANON_KEY` em `.env.local` e reinicie `npm run dev`. Variáveis públicas são incorporadas no build; alterar o arquivo sem reiniciar não atualiza o cliente.

## A extração real não está configurada

Defina uma destas opções e reinicie o frontend:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

ou:

```env
NEXT_PUBLIC_EXTRACAO_PDF_API_URL=http://localhost:8000/api/extracao-pdf/process
```

A URL completa tem precedência.

## Erro de CORS

Confira `FRONTEND_ORIGIN` no backend. Múltiplas origens devem ser separadas por vírgula e precisam coincidir com protocolo, domínio e porta usados pelo navegador.

Depois de alterar, reinicie a API.

## Login funciona, mas a API aceita chamadas sem sessão

Confirme `SUPABASE_URL`, `SUPABASE_ANON_KEY` e o Bearer enviado pelo frontend. Se `AUTH_REQUIRED=true` e as credenciais estiverem ausentes, a API responde 503; token ausente, inválido ou expirado responde 401.

## Perfil não carrega

Verifique:

- se existe linha em `public.profiles` com o mesmo UUID de `auth.users`;
- se a política `profiles_select` permite a leitura;
- a divergência atual entre o campo `role` consultado pelo frontend e a coluna `cargo` existente no banco.

Enquanto o perfil não é carregado, a interface usa o e-mail autenticado.

## Progresso retorna 404

O identificador deve ser o mesmo enviado em `X-Processing-Id`, possuir de 8 a 100 caracteres e conter somente letras, números, `_` ou `-`.

O estado expira após uma hora e é perdido ao reiniciar a API. Em múltiplas instâncias, a consulta pode chegar a uma instância diferente daquela que iniciou o processamento.

## Arquivo recusado

- extensões aceitas: PDF, DOC e DOCX;
- padrão: até 20 arquivos;
- padrão: até 25 MB por arquivo;
- arquivo vazio, corrompido ou com assinatura incompatível é rejeitado;
- PDF escaneado sem texto não possui OCR.

Os limites podem mudar por `MAX_FILES` e `MAX_FILE_SIZE_MB`.

## Ollama não responde

Confirme que o serviço está ativo, que o modelo de `OLLAMA_MODEL` está instalado e que `OLLAMA_BASE_URL` termina no endpoint compatível esperado.

Revise `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_MAX_REQUEST_SECONDS` e os logs da API. Para produção, prefira o provedor configurado para o ambiente em vez de aumentar timeouts indefinidamente.

## OpenRouter falha

Confirme `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY` e `OPENROUTER_MODEL`. Não registre a chave nos logs e não a envie ao frontend.

Falhas isoladas de lote podem gerar arquivo parcial. Confira `X-Extraction-Partial`, `X-Extraction-Failures` e o nome `matriz_priorizacao_parcial.*`.

## Regras do parser não surtem efeito

1. Confirme `ativo = true`.
2. Verifique `escopo`, `categoria` e compatibilidade da regex com Python.
3. Lembre que regex correspondente precede fallback categórico.
4. Em conflitos do mesmo grupo, vence `updated_at` mais recente; `ordem` é o último desempate.
5. Reinicie o processamento; regras são consultadas por requisição, não pela tela do Supabase.
6. Use `/api/extracao-pdf/debug` com documento não sensível para conferir regras selecionadas.

Consulte [../backend/supabase/README.md](../backend/supabase/README.md).

## Supabase não responde no backend

Confirme `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`. Sem configuração, o backend segue sem regras remotas; uma falha de rede também gera fallback seguro e log de exceção.

Não substitua a service role por uma chave pública esperando o mesmo comportamento: as políticas RLS podem limitar os dados.

## Testes demoram ou acessam serviços externos

Execute primeiro os testes diretamente relacionados à alteração. O repositório ainda contém testes e serviços do pipeline anterior, e alguns caminhos podem depender de configuração externa. Não trate build ou `compileall` como prova de integração real com Supabase, Ollama ou OpenRouter.

## Logs no Docker

Com Traefik:

```bash
docker compose -f docker-compose.hostinger.yml logs --tail=200 -f api
```

Com Caddy:

```bash
docker compose logs --tail=200 -f api caddy
```

