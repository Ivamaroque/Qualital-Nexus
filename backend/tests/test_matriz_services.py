import csv
import io
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.csv_service import CSV_COLUMNS, gerar_csv_matriz
from app.main import StatusPollingAccessFilter
from app.services.llm_service import (
    LLMConversionError,
    _criar_prompt,
    _normalizar_ordens_da_resposta,
    _matriz_de_conteudo_json,
    _solicitar_ollama_em_stream,
    _validar_cobertura_dos_blocos,
    converter_blocos_com_ia,
)
from app.services.normalizer_service import normalizar_linhas
from app.services.parser_rules_service import filtrar_regras_por_bloco, preparar_blocos_para_ia
from app.services.pdf_service import limpar_texto_pdf, separar_blocos
from app.schemas.matriz import MatrizLinha, MatrizOutput
from app.services.processing_status import (
    atualizar_processamento,
    concluir_processamento,
    iniciar_processamento,
    obter_processamento,
)
from app.routers.extracao_pdf import _agrupar_blocos, _exemplos_parser_do_lote, _mensagem_progresso_ollama


class MatrizServicesTest(unittest.TestCase):
    def test_ollama_json_response_is_validated(self):
        matriz = _matriz_de_conteudo_json(
            '```json\n{"linhas":[{"ordemBloco":1,"descricao":"Executar rotina","tipoTarefa":"Execução"}]}\n```'
        )

        self.assertEqual(matriz.linhas[0].descricao, "Executar rotina")

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
        self.assertEqual(prompt["exemplos_parser"][0]["nome"], "Como fazer")
        self.assertNotIn("exemplo_saida_json", prompt["regras_parser"][0])
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
        self.assertEqual(conversor.call_args_list[1].args[0]["blocos"], [{"ordem": 2, "texto": "Segundo"}])

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

        self.assertEqual(conversor.call_count, 3)
        self.assertEqual(linhas[0]["ordemBloco"], 14)
        self.assertEqual(linhas[0]["tipoTarefa"], "Título/Subtítulo")
        self.assertEqual(linhas[0]["descricao"], "4.1.2 - Requisito técnico")

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
        concluir_processamento(identificador)

        processamento = obter_processamento(identificador)

        self.assertIsNotNone(processamento)
        self.assertEqual(processamento["status"], "concluido")
        self.assertEqual(processamento["etapa"], "concluido")
        self.assertEqual(processamento["arquivo_atual"], 2)
        self.assertEqual(processamento["lote_atual"], 3)
        self.assertEqual(processamento["etapas_concluidas"], 10)
        self.assertEqual(processamento["etapas_totais"], 10)
        self.assertEqual(processamento["progresso_percentual"], 100)

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

        self.assertEqual([bloco["ordem"] for bloco in blocos], [1, 2, 3])
        self.assertEqual(blocos[1]["categoria"], "objetivo")
        self.assertEqual(blocos[2]["categoria"], "como_fazer")
        self.assertEqual(blocos[2]["escopo"], "anexo_b")
        self.assertNotIn("Aprovado", "\n".join(bloco["texto"] for bloco in blocos))

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

    def test_pdf_parser_extracts_hierarchical_item_for_section_titles(self):
        blocos = separar_blocos("3.2 - Atividade\nFluxo das atividades.\n3.2.1 - Responsável\nTécnico de operação.")

        self.assertEqual([bloco["itemPadraoDetectado"] for bloco in blocos], ["3.2", "3.2.1"])

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
        self.assertEqual(rows[1]["Descrição"], "Executar atividade")
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
