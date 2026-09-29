-- Regras base observadas nos documentos de referência Petro-HRA.
-- Execute este arquivo no SQL Editor do projeto Supabase depois de criar
-- a tabela parser_rules usada pelo backend.

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
