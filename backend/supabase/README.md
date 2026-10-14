# Regras do parser

`public.parser_rules` orienta a classificação dos blocos extraídos antes do envio ao LLM. O backend lê apenas regras com `ativo = true`; desative regras substituídas em vez de apagá-las, para preservar o histórico.

## Precedência

Para cada bloco, o backend aplica esta ordem:

1. regras cuja regex corresponde ao texto; se nenhuma corresponder, usa regras da categoria como fallback;
2. categoria exata do bloco;
3. regra com `updated_at` mais recente, quando duas regras do mesmo grupo conflitam;
4. menor valor de `ordem`, como desempate editorial.

O escopo também precisa ser compatível. Uma regra de `anexo` vale para seus subescopos; uma regra de `geral` só participa quando sua categoria for compatível.

## Campos

| Campo | Uso |
|---|---|
| `nome` | Nome humano e único da regra. |
| `descricao` | Explica quando aplicar e qual resultado esperar. |
| `ativo` | Controla se o backend carrega a regra. |
| `ordem` | Desempate editorial; valores menores vêm primeiro quando as datas empatam. |
| `escopo` | Região do documento: `geral`, `documento_principal`, `anexo`, `tabela_2`, `tabela_5` etc. |
| `categoria` | Categoria produzida pelo parser local. É a principal chave de compatibilidade. |
| `padrao_regex` | Regex opcional, compatível com Python. Vazio significa que a regra é aplicada pela categoria. |
| `tipo_tarefa` | Saída permitida: `Padrão/Anexo`, `Título/Subtítulo`, `Informação`, `Execução` ou `Ignorar`. |
| `exemplo_entrada` | Menor trecho que demonstra a regra. |
| `exemplo_saida_json` | Resultado esperado para orientar o LLM e os testes. |
| `updated_at` | Versão efetiva da regra e critério de precedência em conflitos. |

## Como alterar

1. Confirme a categoria e o escopo produzidos pelo parser local.
2. Prefira ajustar uma regra existente a criar outra equivalente.
3. Use regex somente quando ela realmente restringir a aplicação; regras puramente categóricas devem manter `padrao_regex = ''`.
4. Preencha um exemplo mínimo de entrada e a saída esperada.
5. Execute os testes do backend e valide a regra com um documento real.
6. Em substituições, desative a regra antiga e registre a sucessora na descrição.

O gatilho `trg_parser_rules_updated_at` atualiza `updated_at` somente quando o conteúdo muda. O índice `uq_parser_rules_nome_ci` impede nomes duplicados desconsiderando maiúsculas e minúsculas.

## Auditoria rápida

```sql
-- Regras ativas na ordem em que são mantidas.
select nome, escopo, categoria, tipo_tarefa, ordem, updated_at
from public.parser_rules
where ativo
order by categoria, updated_at desc, ordem;

-- Regras categóricas, sem regex.
select nome, escopo, categoria
from public.parser_rules
where ativo and padrao_regex = '';

-- Ordens repetidas são permitidas, pois data e categoria resolvem a precedência.
select ordem, count(*), array_agg(nome order by updated_at desc)
from public.parser_rules
where ativo
group by ordem
having count(*) > 1;
```
