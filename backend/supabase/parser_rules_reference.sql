-- Regras base observadas nos documentos de referência Petro-HRA.
-- Este arquivo serve como carga inicial e manutenção idempotente. Consulte
-- README.md antes de criar ou alterar regras no projeto Supabase.

WITH regras (nome, descricao, ordem, escopo, padrao_regex, tipo_tarefa, categoria, exemplo_entrada, exemplo_saida_json) AS (
    VALUES
    (
        'ruido_metadado_documento',
        'Ignora cabeçalhos, rodapés, metadados de capa e legendas de figuras que não são tarefas.',
        10,
        'geral',
        '(?i)^\s*(?:INSTALAÇÃO|ÁREA|DATA|RESP(?:ONSÁVEIS)?|NOME|MATR[IÍ]CULA|FUNÇÃO|GERÊNCIA|A[CÇ][AÃ]O\s+DE\s+RTA|FIGURA\s+\d+|\d+\s+DE\s+\d+).*$',
        'Ignorar',
        'fragmento_interface',
        'INSTALAÇÃO P71 ÁREA: Manutenção DATA 22/12/2022',
        '{"linhas":[]}'
    ),
    (
        'ruido_fluxograma_interface',
        'Descarta estados, responsáveis e rótulos isolados gerados pela leitura linear de fluxogramas.',
        20,
        'anexo_fluxograma',
        '(?i)^\s*(?:SIM|NÃO|NAO|RESP\.?|N\.?A\.?|#?\s*INTERNA)\s*$',
        'Ignorar',
        'fragmento_interface',
        'SIM',
        '{"linhas":[]}'
    ),
    (
        'cabecalho_documento_repetido',
        'Não duplica o cabeçalho institucional repetido em páginas de anexos.',
        30,
        'anexo',
        '(?i)^\s*(?:PE|PG|PR|PP)-[A-Z0-9]+-\d{5}\b.*$',
        'Ignorar',
        'cabecalho_documento_repetido',
        'PE-3UBS-01699',
        '{"linhas":[]}'
    ),
    (
        'anexo_cabecalho_repetido',
        'Não cria uma nova linha para o título do anexo repetido no corpo do padrão.',
        40,
        'anexo',
        '(?i)^\s*ANEXO\s+[A-Z]\d*\b.*$',
        'Ignorar',
        'anexo_cabecalho_repetido',
        'ANEXO M1',
        '{"linhas":[]}'
    ),
    (
        'cabecalho_tabela',
        'Cabeçalhos de tabelas servem para orientar a extração, não são tarefas.',
        50,
        'geral',
        '(?i)^\s*(?:O QUE FAZER|EXECUTANTE|ONDE REGISTRAR|ITEM|DESCRIÇÃO|RESPONSÁVEL).*$',
        'Ignorar',
        'cabecalho_tabela',
        'O QUE FAZER | EXECUTANTE | ONDE REGISTRAR',
        '{"linhas":[]}'
    ),
    (
        'padrao_documento',
        'Conserva a identificação do padrão como raiz da matriz.',
        60,
        'documento_principal',
        '(?i)^\s*(?:PE|PG|PR|PP)-[A-Z0-9]+-\d{5}\b.*$',
        'Padrão/Anexo',
        'padrao_documento',
        'PE-3P53-00047 – Versão 14.00 – Padrão Ativo',
        '{"linhas":[{"tipoTarefa":"Padrão/Anexo"}]}'
    ),
    (
        'anexo_documento',
        'Conserva a identificação de anexos reais como raiz independente.',
        70,
        'anexo',
        '(?i)^\s*ANEXO\s+[A-Z]\d*\b.*$',
        'Padrão/Anexo',
        'anexo_documento',
        'ANEXO C - Instruções para partida',
        '{"linhas":[{"tipoTarefa":"Padrão/Anexo"}]}'
    ),
    (
        'secao_principal',
        'Seções numeradas do padrão viram títulos e não devem ser parafraseadas.',
        80,
        'documento_principal',
        '(?i)^\s*\d+\.\s+(?:OBJETIVO|APLICAÇÃO|DESCRIÇÃO|REGISTROS|DEFINIÇÕES)\s*$',
        'Título/Subtítulo',
        'secao_principal',
        '1. OBJETIVO',
        '{"linhas":[{"tipoTarefa":"Título/Subtítulo"}]}'
    ),
    (
        'instrucao_operacional',
        'Ações, verificações e condições operacionais permanecem como execução, preservando o texto de origem.',
        90,
        'geral',
        '(?i)\b(?:verificar|confirmar|acionar|abrir|fechar|alinhar|realizar|informar|solicitar|inspecionar|monitorar)\b',
        'Execução',
        'instrucao_operacional',
        'Verificar a pressão antes de iniciar.',
        '{"linhas":[{"tipoTarefa":"Execução"}]}'
    ),
    (
        'Ação operacional na voz passiva',
        'Reconhece ações operacionais expressas na voz passiva com os modais deve ou pode.',
        216,
        'geral',
        '(?i)(?:^|\W)(?:deve|devem|pode|podem)\s+ser\s+(?:acionad|avaliad|parad|realizad|registrad)[oa]s?(?:$|\W)',
        'Execução',
        'instrucao_operacional',
        'A bomba deve ser parada após a normalização do nível.',
        '{"linhas":[{"tipoTarefa":"Execução"}]}'
    ),
    (
        'Observações e alertas',
        'Mantém observações e notas como informação mesmo quando citam uma ação possível.',
        180,
        'geral',
        '(?im)^\s*(?:OBS(?:ERVA(?:[CÇ][AÃ]O|CAO))?\.?|NOTA|ATEN[CÇ][AÃ]O|LEMBRE-SE)\s*\d*\.?\s*:?.+',
        'Informação',
        'aviso_informativo',
        'NOTA: Em qualquer situação o operador poderá alinhar as bombas.',
        '{"linhas":[{"tipoTarefa":"Informação"}]}'
    ),
    (
        'Legenda de tela operacional',
        'Mantém legendas de telas e fluxogramas como informação, sem interpretar palavras do título como verbos.',
        71,
        'geral',
        '(?i)^\s*TELA\s+\d+\s*[:\-–—]',
        'Informação',
        'legenda_figura',
        'Tela 03: Esgotamento Casa de Bombas - Parte Inferior da tela.',
        '{"linhas":[{"tipoTarefa":"Informação"}]}'
    ),
    (
        'lista_informativa',
        'Listas de recursos, premissas e referências permanecem informativas quando não contêm ação explícita.',
        100,
        'geral',
        '',
        'Informação',
        'lista_informativa',
        '• Rádio transceptor UHF',
        '{"linhas":[{"tipoTarefa":"Informação"}]}'
    ),
    (
        'tabela_tecnica',
        'Parâmetros, limites e tabelas técnicas são informação e não passos operacionais.',
        110,
        'tabelas_tecnicas',
        '',
        'Informação',
        'tabela_tecnica',
        'Pressão da água na entrada | 70 kPa',
        '{"linhas":[{"tipoTarefa":"Informação"}]}'
    ),
    (
        'atividade_tabela_2',
        'Atividades da tabela de análise são títulos; COMO FAZER e PORQUE FAZER são tratados pelas regras específicas.',
        120,
        'tabela_2',
        '',
        'Título/Subtítulo',
        'atividade_tabela_2',
        '1 - Partir a bomba',
        '{"linhas":[{"tipoTarefa":"Título/Subtítulo"}]}'
    ),
    (
        'como_fazer',
        'Conteúdo COMO FAZER é execução vinculada à atividade da tabela.',
        130,
        'tabela_2',
        '(?i)^\s*COMO\s+FAZER\s*:',
        'Execução',
        'como_fazer',
        'COMO FAZER: abrir a válvula.',
        '{"linhas":[{"tipoTarefa":"Execução"}]}'
    ),
    (
        'porque_fazer',
        'Conteúdo PORQUE FAZER explica a finalidade e é informação vinculada à atividade.',
        140,
        'tabela_2',
        '(?i)^\s*PORQUE\s+FAZER\s*:',
        'Informação',
        'porque_fazer',
        'PORQUE FAZER: evitar retorno de fluxo.',
        '{"linhas":[{"tipoTarefa":"Informação"}]}'
    )
)
INSERT INTO public.parser_rules (
    nome, descricao, ordem, escopo, padrao_regex, tipo_tarefa, categoria, exemplo_entrada, exemplo_saida_json, ativo
)
SELECT r.nome, r.descricao, r.ordem, r.escopo, r.padrao_regex, r.tipo_tarefa, r.categoria, r.exemplo_entrada, r.exemplo_saida_json, true
FROM regras AS r
WHERE NOT EXISTS (
    SELECT 1 FROM public.parser_rules existente WHERE existente.nome = r.nome
);

UPDATE public.parser_rules
SET descricao = 'Observações, notas e alertas devem permanecer como Informação, mesmo quando citam uma ação possível.',
    ordem = 180,
    escopo = 'geral',
    padrao_regex = '(?im)^\s*(?:OBS(?:ERVA(?:[CÇ][AÃ]O|CAO))?\.?|NOTA|ATEN[CÇ][AÃ]O|LEMBRE-SE)\s*\d*\.?\s*:?.+',
    tipo_tarefa = 'Informação',
    categoria = 'aviso_informativo',
    ativo = true
WHERE nome = 'Observações e alertas';

UPDATE public.parser_rules
SET descricao = 'Reconhece ações operacionais expressas na voz passiva com os modais deve ou pode.',
    ordem = 216,
    escopo = 'geral',
    padrao_regex = '(?i)(?:^|\W)(?:deve|devem|pode|podem)\s+ser\s+(?:acionad|avaliad|parad|realizad|registrad)[oa]s?(?:$|\W)',
    tipo_tarefa = 'Execução',
    categoria = 'instrucao_operacional',
    ativo = true
WHERE nome = 'Ação operacional na voz passiva';

UPDATE public.parser_rules
SET descricao = 'Mantém legendas de telas e fluxogramas como Informação, sem interpretar palavras do título como verbos.',
    ordem = 71,
    escopo = 'geral',
    padrao_regex = '(?i)^\s*TELA\s+\d+\s*[:\-–—]',
    tipo_tarefa = 'Informação',
    categoria = 'legenda_figura',
    ativo = true
WHERE nome = 'Legenda de tela operacional';

-- Metadados de manutenção: preservam o contrato consumido pelo backend e
-- explicam os campos diretamente no catálogo do Postgres/Supabase Studio.
COMMENT ON TABLE public.parser_rules IS
    'Regras do parser. Seleção: regex correspondente ou fallback por categoria; depois categoria exata, updated_at recente e ordem crescente.';
COMMENT ON COLUMN public.parser_rules.nome IS
    'Nome humano e único da regra.';
COMMENT ON COLUMN public.parser_rules.descricao IS
    'Explica quando aplicar a regra e o resultado esperado.';
COMMENT ON COLUMN public.parser_rules.ativo IS
    'Somente regras ativas são carregadas pelo backend.';
COMMENT ON COLUMN public.parser_rules.ordem IS
    'Desempate editorial após categoria e updated_at; menor valor vence.';
COMMENT ON COLUMN public.parser_rules.escopo IS
    'Região do documento onde a regra pode atuar.';
COMMENT ON COLUMN public.parser_rules.padrao_regex IS
    'Regex compatível com Python; vazio indica aplicação somente pela categoria.';
COMMENT ON COLUMN public.parser_rules.tipo_tarefa IS
    'Classificação final permitida para a linha da matriz.';
COMMENT ON COLUMN public.parser_rules.categoria IS
    'Categoria produzida pelo parser local e usada para compatibilidade.';
COMMENT ON COLUMN public.parser_rules.exemplo_entrada IS
    'Trecho mínimo que demonstra a aplicação da regra.';
COMMENT ON COLUMN public.parser_rules.exemplo_saida_json IS
    'Saída esperada usada como exemplo para o LLM e para validação.';
COMMENT ON COLUMN public.parser_rules.updated_at IS
    'Data da versão efetiva; a regra mais recente vence conflitos compatíveis.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_parser_rules_nome_ci
    ON public.parser_rules (lower(nome));

ALTER FUNCTION public.set_updated_at() SET search_path = '';

DROP TRIGGER IF EXISTS parser_rules_set_updated_at ON public.parser_rules;
DROP TRIGGER IF EXISTS trg_parser_rules_updated_at ON public.parser_rules;
CREATE TRIGGER trg_parser_rules_updated_at
BEFORE UPDATE ON public.parser_rules
FOR EACH ROW
WHEN (OLD IS DISTINCT FROM NEW)
EXECUTE FUNCTION public.set_updated_at();

-- Estas regras já são selecionadas por categoria. As regex anteriores usavam
-- lookbehind de largura variável, que não é aceito pelo runtime Python.
UPDATE public.parser_rules
SET padrao_regex = '',
    descricao = CASE nome
        WHEN 'Texto de objetivo' THEN 'Conteúdo da categoria objetivo. Aplicação pela categoria, sem regex.'
        WHEN 'Texto de aplicação' THEN 'Conteúdo da categoria aplicação. Aplicação pela categoria, sem regex.'
        WHEN 'Itens críticos' THEN 'Conteúdo da categoria itens_criticos. Aplicação pela categoria, sem regex.'
    END
WHERE nome IN ('Texto de objetivo', 'Texto de aplicação', 'Itens críticos');

-- Regra antiga coberta pela versão alfanumérica mais recente. É mantida
-- inativa para histórico e possível reversão.
UPDATE public.parser_rules
SET ativo = false,
    descricao = 'Substituída por Anexo alfanumérico em arquivo próprio.'
WHERE nome = 'Cabeçalho de anexo';
