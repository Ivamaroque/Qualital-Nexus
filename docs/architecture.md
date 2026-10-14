# Arquitetura

## Componentes

```mermaid
flowchart LR
    U[Usuário] --> F[Next.js]
    F -->|login e perfil| S[Supabase Auth/Postgres]
    F -->|multipart + JWT| A[FastAPI]
    A -->|regras do parser| S
    A --> E[Extração PDF/Word]
    E --> P[Parser local]
    P --> L[Ollama ou OpenRouter]
    L --> N[Normalização e hierarquia]
    N --> X[XLSX ou CSV]
    X --> F
```

O frontend e o backend são aplicações independentes. O frontend autentica o usuário no Supabase e chama a API configurada por variável de ambiente. O backend usa uma chave privilegiada para consultar as regras do parser e não deve expor essa chave ao navegador.

## Fluxo da extração

1. O usuário entra com e-mail e senha no Supabase.
2. A tela de extração valida a extensão e mantém a ordem visual dos arquivos.
3. O frontend envia os arquivos como partes `files[]`, na ordem apresentada.
4. Quando há callback de progresso, o frontend gera um `X-Processing-Id` e consulta o endpoint de status a cada 1,25 segundo.
5. O backend valida quantidade e tamanho, extrai texto, tabelas e imagens e separa o conteúdo em blocos.
6. As regras ativas de `public.parser_rules` orientam a categoria e o tipo de tarefa de cada bloco.
7. Os blocos textuais são agrupados em lotes e enviados ao provedor LLM configurado.
8. O backend corrige cobertura, aplica fallbacks determinísticos, consolida a hierarquia e normaliza as colunas.
9. Imagens relevantes são preservadas como linhas informativas no XLSX.
10. A API devolve XLSX ou CSV. Se somente alguns lotes da IA falharem, devolve um arquivo parcial e sinaliza a condição nos headers.

## Responsabilidades

| Camada | Responsabilidade | Entrada/saída principal |
|---|---|---|
| Next.js | Sessão, fila, progresso e download | Arquivos do usuário e Blob retornado pela API |
| FastAPI/router | Orquestração, erros e resposta HTTP | Multipart e XLSX/CSV |
| Extração | Leitura de PDF, DOC e DOCX | Bytes e blocos textuais/visuais |
| Parser local | Categoria, escopo, item e palavras-chave | Blocos estruturados |
| Supabase | Auth, perfil e regras configuráveis | JWT, perfil e `parser_rules` |
| LLM | Conversão semântica dos blocos | JSON validado da matriz |
| Pós-processamento | Granularidade, executante e hierarquia | Linhas finais normalizadas |

## Estado e escalabilidade

O progresso fica em memória no processo FastAPI e expira após uma hora. Reiniciar a API perde os estados em andamento. Múltiplas réplicas também exigiriam armazenamento compartilhado ou afinidade de sessão; o desenho atual é apropriado para uma única instância.

Os arquivos são processados durante a própria requisição. Não existe fila persistente, worker separado ou histórico de execuções.

## Caminho ativo e código legado

O endpoint atual usa `routers/extracao_pdf.py`, `document_service.py`, `pdf_service.py`, `parser_rules_service.py`, `llm_service.py`, `matrix_structure_service.py`, `normalizer_service.py`, `xlsx_service.py` e `csv_service.py`.

`extraction_service.py`, `file_extractor.py`, `parser_rules.py`, `ai_service.py`, `markdown_converter.py` e `csv_generator.py` formam um fluxo anterior. Eles não são chamados pelas rotas atuais, embora parte deles ainda tenha testes. Não implemente novas regras nesse caminho sem antes decidir se ele será removido ou reativado.

## Limitações conhecidas

- PDF sem camada de texto não possui OCR.
- O progresso não é persistente nem distribuído.
- A API ainda não aplica a função existente de validação do JWT às rotas.
- O schema completo do Supabase ainda não possui migrations reproduzíveis no repositório.
- O frontend não possui suíte automatizada nem lint configurado.

