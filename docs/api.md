# API

Base local: `http://localhost:8000`.

As rotas de extração validam o Bearer token no Supabase Auth. Apenas o endpoint de saúde é público. No desenvolvimento sem Supabase, defina `AUTH_REQUIRED=false` explicitamente.

## `GET /health`

Resposta:

```json
{"status":"ok"}
```

## `POST /api/extracao-pdf/process`

Processa um ou mais documentos e devolve um arquivo.

### Query parameters

| Parâmetro | Valores | Padrão | Uso |
|---|---|---|---|
| `format` | `xlsx`, `csv` | `xlsx` | Formato do download. |
| `table_mode` | `imagem`, `texto` | `imagem` | Forma de tratar tabelas extraídas. |

### Headers

| Header | Obrigatório | Uso |
|---|---:|---|
| `Authorization: Bearer <JWT>` | Sim¹ | Sessão validada no Supabase Auth. |
| `X-Processing-Id` | Não | Identificador de 8 a 100 caracteres alfanuméricos, `_` ou `-`, usado para polling. |

¹ Dispensado somente no modo local explicitamente configurado com `AUTH_REQUIRED=false` e sem credenciais de Auth.

### Corpo

`multipart/form-data` com uma ou mais partes `files[]`. O nome legado `files` também é aceito. A ordem das partes define a ordem dos documentos.

```bash
curl -X POST "http://localhost:8000/api/extracao-pdf/process?format=xlsx&table_mode=imagem" \
  -H "Authorization: Bearer $SUPABASE_USER_JWT" \
  -H "X-Processing-Id: exemplo-processamento-001" \
  -F "files[]=@procedimento.pdf" \
  -F "files[]=@anexo.docx" \
  --output matriz_priorizacao.xlsx
```

### Resposta

- XLSX: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- CSV: `text/csv; charset=utf-8`.

Headers relevantes:

| Header | Exemplo | Uso |
|---|---|---|
| `Content-Disposition` | `attachment; filename="matriz_priorizacao.xlsx"` | Nome do arquivo. |
| `X-Extraction-Format` | `xlsx` | Formato solicitado. |
| `X-Extraction-Partial` | `false` | Indica saída parcial. |
| `X-Extraction-Failures` | `0` | Quantidade de lotes da IA sem saída. |

Quando há falhas parciais, o nome começa com `matriz_priorizacao_parcial`.

## `GET /api/extracao-pdf/process/{id}/status`

Retorna o progresso associado ao `X-Processing-Id`.

```json
{
  "status": "processando",
  "etapa": "ia",
  "mensagem": "A IA está gerando linhas para o lote 1 de 2.",
  "arquivo_atual": 1,
  "total_arquivos": 2,
  "lote_atual": 1,
  "total_lotes": 2,
  "etapas_concluidas": 4,
  "etapas_totais": 8,
  "progresso_percentual": 50,
  "ia_status": "gerando_resposta",
  "ia_trechos_recebidos": 3,
  "ia_caracteres_recebidos": 2800,
  "atualizado_em": "2026-10-14T16:00:00+00:00"
}
```

Estados: `processando`, `concluido` ou `erro`. O registro expira uma hora após a última atualização e é perdido se o processo reiniciar.

Responde 404 para ID inválido, expirado ou inexistente.

## `POST /api/extracao-pdf/debug`

Aceita os mesmos arquivos e `table_mode`, mas retorna JSON com:

- arquivos e blocos processados;
- categorias e escopos;
- regras usadas por bloco;
- quantidade de exemplos do parser;
- prévia das linhas;
- lotes que falharam;
- modo de tabela utilizado.

Use apenas para diagnóstico: a resposta pode ser grande e conter conteúdo dos documentos.

## Erros

| Status | Situação típica |
|---:|---|
| 400 | Nenhum arquivo, limite excedido, extensão inválida, arquivo vazio/corrompido ou nenhum bloco identificado. |
| 404 | Status inexistente ou expirado. |
| 401 | Bearer ausente, inválido ou expirado. |
| 503 | Supabase Auth indisponível ou configuração obrigatória ausente. |
| 500 | Falha interna não convertida em erro de domínio. |

O detalhe de erros HTTP é retornado em JSON no campo `detail`.
