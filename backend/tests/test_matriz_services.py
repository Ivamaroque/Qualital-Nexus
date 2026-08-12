import csv
import io
import logging
import sys
import unittest
from asyncio import run
from pathlib import Path
from unittest.mock import patch

from starlette.datastructures import UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.csv_service import CSV_COLUMNS, gerar_csv_matriz
from app.main import StatusPollingAccessFilter
from app.services.llm_service import (
    LLMConversionError,
    _criar_linhas_de_fallback,
    _criar_prompt,
    _normalizar_ordens_da_resposta,
    _preencher_item_padrao_detectado,
    _remover_linhas_nao_fundamentadas,
    _matriz_de_conteudo_json,
    _solicitar_ollama_em_stream,
    _validar_cobertura_dos_blocos,
    converter_blocos_com_ia,
)
from app.services.matrix_structure_service import consolidar_hierarquia_tarefas
from app.services.normalizer_service import normalizar_linhas
from app.services.parser_rules_service import filtrar_regras_por_bloco, preparar_blocos_para_ia
from app.services.pdf_service import _serializar_tabela, limpar_texto_pdf, separar_blocos
from app.schemas.matriz import MatrizLinha, MatrizOutput
from app.services.processing_status import (
    atualizar_processamento,
    concluir_processamento,
    iniciar_processamento,
    obter_processamento,
)
from app.routers.extracao_pdf import (
    _agrupar_blocos,
    _exemplos_parser_do_lote,
    _mensagem_progresso_ollama,
    _processar_arquivos,
)


class MatrizServicesTest(unittest.TestCase):
    def test_ollama_json_response_is_validated(self):
        matriz = _matriz_de_conteudo_json(
            '```json\n{"linhas":[{"ordemBloco":1,"descricao":"Executar rotina","tipoTarefa":"Execução"}]}\n```'
        )

        self.assertEqual(matriz.linhas[0].descricao, "Executar rotina")

    def test_ollama_legacy_ordem_field_is_mapped_to_ordem_bloco(self):
        matriz = _matriz_de_conteudo_json(
            '{"linhas":[{"ordem":9,"descricao":"Atividade","tipoTarefa":"Execução"}]}'
        )

        self.assertEqual(matriz.linhas[0].ordemBloco, 9)

    def test_processing_continues_after_a_failed_llm_batch(self):
        blocos = [
            {
                "ordem": ordem,
                "texto": f"Bloco {ordem}",
                "categoria": "geral",
                "escopo": "documento_principal",
                "palavras_chave": [],
            }
            for ordem in range(1, 10)
        ]
        arquivo = UploadFile(filename="teste.pdf", file=io.BytesIO(b"%PDF-1.4 teste"))

        with (
            patch("app.routers.extracao_pdf.extrair_texto_pdf", return_value="texto"),
            patch("app.routers.extracao_pdf.limpar_texto_pdf", return_value="texto"),
            patch("app.routers.extracao_pdf.separar_blocos", return_value=blocos),
            patch("app.routers.extracao_pdf.buscar_parser_rules", return_value=[]),
            patch(
                "app.routers.extracao_pdf.converter_blocos_com_ia",
                side_effect=[
                    LLMConversionError("resposta inválida"),
                    [{"descricao": "Bloco 9", "tipoTarefa": "Informação"}],
                ],
            ),
        ):
            linhas, debug = run(_processar_arquivos([arquivo], incluir_debug=False))

        self.assertEqual([linha["descricao"] for linha in linhas], ["Bloco 9"])
        self.assertEqual(debug["falhas_lotes"][0]["ordens_blocos"], list(range(1, 9)))

    def test_prompt_uses_examples_from_selected_parser_rules(self):
        regras = [
            {
                "nome": "Como fazer",
                "exemplo_entrada": "COMO FAZER: Registrar a atividade.",
                "exemplo_saida_json": [{"descricao": "Registrar a atividade.", "tipoTarefa": "Execução"}],
            },
            {"nome": "Sem exemplo"},
        ]

        exemplos = _exemplos_parser_do_lote(regras)
        prompt = _criar_prompt([{"ordem": 9}], regras, exemplos, {"filename": "teste.pdf", "file_order": 1})

        self.assertEqual(len(exemplos), 1)
        self.assertEqual(prompt["exemplos_parser"][0]["entrada"], "COMO FAZER: Registrar a atividade.")
        self.assertNotIn("nome", prompt["orientacoes_parser"][0])
        self.assertNotIn("exemplos_rag", prompt)
        self.assertEqual(prompt["ordensBlocoPermitidas"], [9])

    def test_parser_adds_matching_rule_orientation_to_each_block(self):
        blocos = [
            {"ordem": 1, "texto": "COMO FAZER: Registrar a atividade.", "escopo": "geral", "categoria": "como_fazer"}
        ]
        regras = [
            {
                "nome": "Como fazer",
                "escopo": "geral",
                "categoria": "como_fazer",
                "tipo_tarefa": "Execução",
                "padrao_regex": r"(?i)^COMO FAZER:",
                "ordem": 1,
            }
        ]

        resultado = preparar_blocos_para_ia(blocos, regras)

        self.assertEqual(resultado[0]["orientacao_parser"]["regra"], "Como fazer")
        self.assertEqual(resultado[0]["orientacao_parser"]["tipoTarefa"], "Execução")

    def test_parser_does_not_apply_unrelated_ignore_rule(self):
        blocos = [{"ordem": 1, "texto": "1. OBJETIVO", "escopo": "documento_principal", "categoria": "objetivo"}]
        regras = [
            {
                "nome": "Sumário inicial",
                "escopo": "documento_principal",
                "categoria": "ruido_sumario",
                "tipo_tarefa": "Ignorar",
                "padrao_regex": r"(?i)^\s*1\.\s*OBJETIVO\s*$",
                "ordem": 1,
            }
        ]

        resultado = preparar_blocos_para_ia(blocos, regras)

        self.assertIsNone(resultado[0]["orientacao_parser"]["regra"])

    def test_parser_uses_category_orientation_when_rule_requires_missing_table_columns(self):
        blocos = [{"ordem": 1, "texto": "1- Alinhar a chegada de dutos", "escopo": "tabela_2", "categoria": "atividade_tabela_2"}]
        regras = [
            {
                "nome": "Atividade da Tabela 2",
                "escopo": "tabela_2",
                "categoria": "atividade_tabela_2",
                "tipo_tarefa": "Execução",
                "padrao_regex": r"Técnico de operação",
                "ordem": 1,
            }
        ]

        resultado = preparar_blocos_para_ia(blocos, regras)

        self.assertEqual(resultado[0]["orientacao_parser"]["regra"], "Atividade da Tabela 2")

    def test_ia_coverage_rejects_missing_source_block(self):
        matriz = MatrizOutput(linhas=[MatrizLinha(ordemBloco=1, descricao="Executar", tipoTarefa="Execução")])

        with self.assertRaises(LLMConversionError):
            _validar_cobertura_dos_blocos([{"ordem": 1}, {"ordem": 2}], matriz)

    def test_ia_recovers_only_the_missing_blocks_once(self):
        blocos = [{"ordem": 1, "texto": "Primeiro"}, {"ordem": 2, "texto": "Segundo"}]
        primeira_resposta = MatrizOutput(linhas=[MatrizLinha(ordemBloco=1, descricao="Primeiro", tipoTarefa="Informação")])
        segunda_resposta = MatrizOutput(linhas=[MatrizLinha(ordemBloco=2, descricao="Segundo", tipoTarefa="Informação")])

        with patch(
            "app.services.llm_service._converter_prompt",
            side_effect=[primeira_resposta, segunda_resposta],
        ) as conversor:
            linhas = converter_blocos_com_ia(blocos, [], [], {"filename": "teste.pdf", "file_order": 1})

        self.assertEqual([linha["ordemBloco"] for linha in linhas], [1, 2])
        self.assertEqual(conversor.call_count, 2)
        self.assertEqual([bloco["ordem"] for bloco in conversor.call_args_list[1].args[0]["blocos"]], [2])

    def test_ia_converts_local_batch_positions_to_global_block_orders(self):
        blocos = [{"ordem": 9}, {"ordem": 10}, {"ordem": 11}]
        resposta = MatrizOutput(
            linhas=[
                MatrizLinha(ordemBloco=1, descricao="Primeiro", tipoTarefa="Informação"),
                MatrizLinha(ordemBloco=2, descricao="Segundo", tipoTarefa="Informação"),
                MatrizLinha(ordemBloco=3, descricao="Terceiro", tipoTarefa="Informação"),
            ]
        )

        normalizada = _normalizar_ordens_da_resposta(blocos, resposta)

        self.assertEqual([linha.ordemBloco for linha in normalizada.linhas], [9, 10, 11])

    def test_parser_completes_detected_item_on_section_title(self):
        matriz = MatrizOutput(
            linhas=[MatrizLinha(ordemBloco=1, descricao="3.2 - Atividade", tipoTarefa="Título/Subtítulo")]
        )

        resultado = _preencher_item_padrao_detectado(
            [{"ordem": 1, "itemPadraoDetectado": "3.2"}],
            matriz,
        )

        self.assertEqual(resultado.linhas[0].itemPadrao, "3.2")
        self.assertEqual(resultado.linhas[0].descricao, "Atividade")

    def test_parser_discards_metadata_not_found_in_the_source_block(self):
        matriz = MatrizOutput(
            linhas=[MatrizLinha(ordemBloco=1, descricao="Contrato CSV da Matriz", tipoTarefa="Informação")]
        )

        resultado = _remover_linhas_nao_fundamentadas(
            [{"ordem": 1, "texto": "Atualizar a pressão do sistema."}],
            matriz,
        )

        self.assertEqual(resultado.linhas, [])

    def test_ia_recovers_missing_global_orders_from_a_local_retry_response(self):
        blocos = [{"ordem": ordem, "texto": f"Bloco {ordem}"} for ordem in range(9, 17)]
        primeira_resposta = MatrizOutput(
            linhas=[
                MatrizLinha(ordemBloco=ordem, descricao=f"Bloco {ordem}", tipoTarefa="Informação")
                for ordem in range(9, 14)
            ]
        )
        resposta_local_com_excesso = MatrizOutput(
            linhas=[
                MatrizLinha(ordemBloco=ordem, descricao=f"Correção {ordem}", tipoTarefa="Informação")
                for ordem in range(1, 9)
            ]
        )

        with patch(
            "app.services.llm_service._converter_prompt",
            side_effect=[primeira_resposta, resposta_local_com_excesso],
        ) as conversor:
            linhas = converter_blocos_com_ia(blocos, [], [], {"filename": "teste.pdf", "file_order": 1})

        self.assertEqual(conversor.call_count, 2)
        self.assertEqual({linha["ordemBloco"] for linha in linhas}, set(range(9, 17)))

    def test_ia_uses_parser_fallback_after_all_coverage_attempts_fail(self):
        bloco = {"ordem": 14, "texto": "4.1.2 - Requisito técnico", "categoria": "secao_principal"}
        resposta_vazia = MatrizOutput(linhas=[])

        with patch(
            "app.services.llm_service._converter_prompt",
            return_value=resposta_vazia,
        ) as conversor:
            linhas = converter_blocos_com_ia([bloco], [], [], {"filename": "teste.pdf", "file_order": 1})

        self.assertEqual(conversor.call_count, 2)
        self.assertEqual(linhas[0]["ordemBloco"], 14)
        self.assertEqual(linhas[0]["tipoTarefa"], "Título/Subtítulo")
        self.assertEqual(linhas[0]["descricao"], "- Requisito técnico")

    def test_ollama_progress_message_covers_retry_state_and_unknown_states(self):
        self.assertIn("omitiu blocos", _mensagem_progresso_ollama("corrigindo_cobertura"))
        self.assertEqual(
            _mensagem_progresso_ollama("estado_novo"),
            "Ollama está atualizando o processamento do lote.",
        )

    def test_ollama_json_without_linhas_has_clear_error(self):
        with self.assertRaises(LLMConversionError) as context:
            _matriz_de_conteudo_json('{"ordem": "1", "texto": "Conteúdo do PDF"}')

        self.assertIn('chave "linhas"', str(context.exception))

    def test_ollama_stream_reports_real_response_activity(self):
        class RespostaStreamFalsa:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter(
                    [
                        'data: {"choices":[{"delta":{"reasoning":"Analisando o lote"}}]}',
                        'data: {"choices":[{"delta":{"content":"{\\"linhas\\":"}}]}',
                        'data: {"choices":[]}',
                        'data: {"choices":[{"delta":{"content":"[]}"}}]}',
                        "data: [DONE]",
                    ]
                )

        atualizacoes: list[tuple[str, int, int]] = []
        with patch("app.services.llm_service.httpx.stream", return_value=RespostaStreamFalsa()):
            conteudo = _solicitar_ollama_em_stream(
                "http://ollama.test/v1/chat/completions",
                {"model": "modelo-teste"},
                30,
                lambda estado, trechos, caracteres: atualizacoes.append((estado, trechos, caracteres)),
            )

        self.assertEqual(conteudo, '{"linhas":[]}')
        self.assertIn(("conectando", 0, 0), atualizacoes)
        self.assertIn(("aguardando_resposta", 0, 0), atualizacoes)
        self.assertIn(("raciocinando", 0, 0), atualizacoes)
        self.assertIn(("gerando_resposta", 1, 10), atualizacoes)
        self.assertEqual(atualizacoes[-1], ("resposta_completa", 2, 13))

    def test_processing_status_tracks_progress_until_completion(self):
        identificador = "teste-status-123"
        iniciar_processamento(identificador, total_arquivos=2)
        atualizar_processamento(
            identificador,
            "ia",
            "A IA está gerando linhas.",
            arquivo_atual=2,
            total_arquivos=2,
            lote_atual=3,
            total_lotes=4,
            etapas_concluidas=4,
            etapas_totais=10,
        )
        em_andamento = obter_processamento(identificador)
        self.assertIsNotNone(em_andamento)
        self.assertEqual(em_andamento["progresso_percentual"], 40)
        falhas_lotes = [{"lote_order": 2, "ordens_blocos": [9, 10]}]
        concluir_processamento(identificador, "CSV parcial gerado.", falhas_lotes=falhas_lotes)

        processamento = obter_processamento(identificador)

        self.assertIsNotNone(processamento)
        self.assertEqual(processamento["status"], "concluido")
        self.assertEqual(processamento["etapa"], "concluido")
        self.assertEqual(processamento["arquivo_atual"], 2)
        self.assertEqual(processamento["lote_atual"], 3)
        self.assertEqual(processamento["etapas_concluidas"], 10)
        self.assertEqual(processamento["etapas_totais"], 10)
        self.assertEqual(processamento["progresso_percentual"], 100)
        self.assertEqual(processamento["mensagem"], "CSV parcial gerado.")
        self.assertEqual(processamento["falhas_lotes"], falhas_lotes)

    def test_status_polling_access_logs_are_hidden_but_errors_remain_visible(self):
        filtro = StatusPollingAccessFilter()
        sucesso = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            0,
            '127.0.0.1 - "GET /api/extracao-pdf/process/teste-status-123/status HTTP/1.1" 200',
            (),
            None,
        )
        erro = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            0,
            '127.0.0.1 - "GET /api/extracao-pdf/process/teste-status-123/status HTTP/1.1" 404',
            (),
            None,
        )

        self.assertFalse(filtro.filter(sucesso))
        self.assertTrue(filtro.filter(erro))

    def test_batching_preserves_order_and_respects_limit(self):
        blocos = [
            {"ordem": 1, "texto": "aaaa"},
            {"ordem": 2, "texto": "bbb"},
            {"ordem": 3, "texto": "ccccc"},
        ]

        lotes = _agrupar_blocos(blocos, 7)

        self.assertEqual([[bloco["ordem"] for bloco in lote] for lote in lotes], [[1, 2], [3]])

    def test_pdf_cleaning_and_block_order(self):
        texto = "INTERNA\nPágina 1 de 2\nANEXO B\n1. OBJETIVO\nDefinir o fluxo.\n\nCOMO FAZER\nExecutar a rotina.\nAprovado por: qualidade"

        blocos = separar_blocos(limpar_texto_pdf(texto))

        self.assertEqual([bloco["ordem"] for bloco in blocos], [1, 2, 3, 4])
        self.assertEqual(blocos[1]["categoria"], "secao_principal")
        self.assertEqual(blocos[2]["texto"], "Definir o fluxo.")
        self.assertEqual(blocos[3]["categoria"], "como_fazer")
        self.assertEqual(blocos[3]["escopo"], "anexo_b")
        self.assertNotIn("Aprovado", "\n".join(bloco["texto"] for bloco in blocos))

    def test_pdf_parser_removes_repeated_initial_table_of_contents(self):
        texto = (
            "PE-3UBA-00263\n1. OBJETIVO\n2. APLICAÇÃO\n3. DESCRIÇÃO\n4. REGISTROS\n5. DEFINIÇÕES\n"
            "1. OBJETIVO\nDescrever o processo.\n2. APLICAÇÃO\nAplicar na unidade."
        )

        blocos = separar_blocos(texto)

        self.assertEqual(
            [bloco["texto"].splitlines()[0] for bloco in blocos],
            ["PE-3UBA-00263", "1. OBJETIVO", "Descrever o processo.", "2. APLICAÇÃO", "Aplicar na unidade."],
        )

    def test_pdf_cleaning_removes_lone_underscore_artifact(self):
        self.assertEqual(limpar_texto_pdf("_\nConteudo valido"), "Conteudo valido")

    def test_pdf_parser_does_not_change_scope_for_anexo_mentioned_in_instruction(self):
        texto = 'Tabela 2 - Etapas\n1- Alinhar dutos\nCOMO FAZER: Seguir o Anexo "A" do procedimento.'

        blocos = separar_blocos(texto)

        self.assertEqual(blocos[-1]["escopo"], "tabela_2")

    def test_pdf_parser_splits_list_items_and_resets_table_scope(self):
        texto = (
            "Tabela 2 - Etapas de execução\n"
            "1- Alinhar a chegada de dutos\n"
            "COMO FAZER: Alinhar o sistema.\n"
            "2- Registrar a atividade\n"
            "3.2.3 - Recursos necessários\n"
            "- Lanterna à prova de explosão"
        )

        blocos = separar_blocos(texto)

        self.assertEqual([bloco["escopo"] for bloco in blocos[:4]], ["tabela_2", "tabela_2", "tabela_2", "tabela_2"])
        self.assertEqual(blocos[4]["escopo"], "documento_principal")
        self.assertEqual(blocos[5]["escopo"], "documento_principal")
        self.assertEqual(blocos[1]["categoria"], "atividade_tabela_2")
        self.assertEqual(blocos[1]["contextoTarefa"], {"itemPadrao": "", "subtarefaHTA": "1."})
        self.assertEqual(blocos[4]["contextoTarefa"], {})

    def test_pdf_parser_extracts_hierarchical_item_for_section_titles(self):
        blocos = separar_blocos("3.2 - Atividade\nFluxo das atividades.\n3.2.1 - Responsável\nTécnico de operação.")

        titulos = [bloco for bloco in blocos if bloco["tituloEstrutural"]]
        self.assertEqual([bloco["itemPadraoDetectado"] for bloco in titulos], ["3.2", "3.2.1"])

    def test_pdf_parser_groups_contiguous_informational_list_in_one_block(self):
        blocos = separar_blocos(
            "3.2.3 - Recursos necessários\n"
            "- Lanterna à prova de explosão;\n"
            "- Rádio e telefone;\n"
            "- Veículo."
        )

        self.assertEqual(len(blocos), 2)
        self.assertTrue(blocos[1]["listaAgrupada"])
        self.assertEqual(blocos[1]["categoria"], "lista_informativa")
        self.assertEqual(blocos[1]["texto"].count("\n"), 2)

    def test_pdf_parser_groups_numbered_list_without_turning_items_into_titles(self):
        blocos = separar_blocos(
            "3.2.9.2 - Ordem de fechamento\n"
            "1 - Campo Alfa\n\n"
            "2 - Campo Beta\n\n"
            "3 - Campo Gama"
        )

        self.assertEqual(len(blocos), 2)
        self.assertTrue(blocos[1]["listaAgrupada"])
        self.assertEqual(blocos[1]["categoria"], "lista_informativa")
        self.assertFalse(blocos[1]["tituloEstrutural"])

    def test_parser_marks_only_explicit_operational_paragraphs_for_ai(self):
        blocos = separar_blocos(
            "3.2.4 - Itens críticos\n"
            "Como boa prática, recomenda-se coletar uma amostra. O supervisor deverá avaliar o retorno.\n"
            "3.2.5 - Indicadores\n"
            "Não devem ser registrados desvios durante manutenção programada."
        )

        self.assertEqual(blocos[1]["categoria"], "instrucao_operacional")
        self.assertNotEqual(blocos[3]["categoria"], "instrucao_operacional")

    def test_operational_fallback_expands_actions_and_assigns_numeric_hta(self):
        blocos = separar_blocos(
            "2.3 - Controle operacional\n"
            "Recomenda-se coletar uma amostra. O supervisor deverá avaliar o retorno."
        )
        linhas = [
            linha.model_dump()
            for bloco in blocos
            for linha in _criar_linhas_de_fallback(bloco)
        ]

        consolidadas = consolidar_hierarquia_tarefas(blocos, linhas)
        execucoes = [linha for linha in consolidadas if linha["tipoTarefa"] == "Execução"]

        self.assertEqual(len(execucoes), 2)
        self.assertEqual([linha["subtarefaHTA"] for linha in execucoes], ["1.1.", "1.2."])
        self.assertTrue(all(linha["itemPadrao"] == "2.3" for linha in execucoes))
        self.assertEqual(consolidadas[0]["subtarefaHTA"], "1.")

    def test_coordinated_actions_repeat_the_full_source_description(self):
        bloco = {
            "ordem": 1,
            "texto": 'COMO FAZER: Lendo e registrando no "Anexo C" os valores.',
            "categoria": "como_fazer",
            "contextoTarefa": {"itemPadrao": "2.3.1", "subtarefaHTA": "1."},
        }

        linhas = _criar_linhas_de_fallback(bloco)

        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0].descricao, linhas[1].descricao)
        self.assertEqual([linha.subtarefaHTA for linha in linhas], ["1.1.", "1.2."])

    def test_operational_table_uses_only_target_matrix_content(self):
        class TabelaFalsa:
            def extract(self):
                return [
                    ["O QUE FAZER", "EXECUTANTE", "ONDE REGISTRAR"],
                    ["1- Alinhar dutos", "Técnico de operação", "Boletim"],
                    ["COMO FAZER: Alinhar.\nPORQUE FAZER: Garantir fluxo.", None, None],
                ]

        texto = _serializar_tabela(TabelaFalsa())

        self.assertIn("1- Alinhar dutos", texto)
        self.assertNotIn("Técnico de operação", texto)
        self.assertNotIn("Boletim\n", texto)
        self.assertIn("COMO FAZER: Alinhar.\n\nPORQUE FAZER: Garantir fluxo.", texto)

    def test_structural_blocks_bypass_ai_and_keep_title_and_content_separate(self):
        blocos = separar_blocos("1. OBJETIVO\nDescrever o processo.")

        with patch("app.services.llm_service._converter_prompt") as conversor:
            titulo = converter_blocos_com_ia([blocos[0]], [], [], {"filename": "teste.pdf"})

        conversor.assert_not_called()
        self.assertEqual(titulo[0]["descricao"], "OBJETIVO")
        self.assertEqual(titulo[0]["tipoTarefa"], "Título/Subtítulo")

    def test_document_header_populates_item_column_and_allows_empty_description(self):
        blocos = separar_blocos(
            "PE-3UBA-00263 – Versão 03.00 – Padrão Ativo\n\n"
            "RECEBIMENTO DE GÁS NATURAL"
        )

        linhas = converter_blocos_com_ia(blocos, [], [], {"filename": "teste.pdf"})
        normalizadas = normalizar_linhas(linhas)

        self.assertEqual(normalizadas[0]["itemPadrao"], "PE-3UBA-00263-03.00 - RECEBIMENTO DE GÁS NATURAL")
        self.assertEqual(normalizadas[0]["descricao"], "")
        self.assertEqual(normalizadas[0]["tipoTarefa"], "Padrão/Anexo")

    def test_normalizer_and_csv_numbering(self):
        linhas = normalizar_linhas(
            [
                {"itemPadrao": "P1", "descricao": " Referência ", "tipoTarefa": "Padrão/Anexo"},
                {
                    "descricao": "Executar\natividade",
                    "tipoTarefa": "Execução",
                    "subtarefaHTA": "Fazer",
                },
                {"descricao": "Ignorar", "tipoTarefa": "Ignorar"},
                {
                    "descricao": "Executar atividade",
                    "tipoTarefa": "Execução",
                    "subtarefaHTA": "Fazer",
                },
            ]
        )

        csv_text = gerar_csv_matriz(linhas)
        rows = list(csv.DictReader(io.StringIO(csv_text.removeprefix("\ufeff")), delimiter=";"))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ID da Subtarefa"], "")
        self.assertEqual(rows[1]["ID da Subtarefa"], "1")
        self.assertEqual(rows[1]["Descrição"], "Executar\natividade")
        self.assertEqual(
            CSV_COLUMNS,
            ("Item (Padrão)", "Descrição", "Tipo da Tarefa", "ID da Subtarefa", "Subtarefa (HTA)", "Descrição da tarefa"),
        )

    def test_rules_prioritize_matching_scope_and_category(self):
        regras = [
            {"id": 1, "escopo": "geral", "categoria": "geral", "ordem": 1},
            {"id": 2, "escopo": "anexo_b", "categoria": "anexo", "ordem": 5},
            {"id": 3, "escopo": "anexo_b", "categoria": "geral", "ordem": 2},
        ]

        selecionadas = filtrar_regras_por_bloco(regras, "anexo_b", "anexo")

        self.assertEqual([regra["id"] for regra in selecionadas], [2, 1, 3])


if __name__ == "__main__":
    unittest.main()
