import csv
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.csv_service import gerar_csv_matriz
from app.services.llm_service import _matriz_de_conteudo_json
from app.services.normalizer_service import normalizar_linhas
from app.services.parser_rules_service import filtrar_regras_por_bloco
from app.services.pdf_service import limpar_texto_pdf, separar_blocos
from app.routers.extracao_pdf import _agrupar_blocos


class MatrizServicesTest(unittest.TestCase):
    def test_ollama_json_response_is_validated(self):
        matriz = _matriz_de_conteudo_json(
            '```json\n{"linhas":[{"descricao":"Executar rotina","tipoTarefa":"Execução"}]}\n```'
        )

        self.assertEqual(matriz.linhas[0].descricao, "Executar rotina")

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

    def test_normalizer_and_csv_numbering(self):
        linhas = normalizar_linhas(
            [
                {"itemPadrao": "P1", "descricao": " Referência ", "tipoTarefa": "Padrão/Anexo"},
                {"descricao": "Executar\natividade", "tipoTarefa": "Execução", "subtarefaHTA": "Fazer"},
                {"descricao": "Ignorar", "tipoTarefa": "Ignorar"},
                {"descricao": "Executar atividade", "tipoTarefa": "Execução", "subtarefaHTA": "Fazer"},
            ]
        )

        csv_text = gerar_csv_matriz(linhas)
        rows = list(csv.DictReader(io.StringIO(csv_text.removeprefix("\ufeff")), delimiter=";"))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ID da Subtarefa"], "")
        self.assertEqual(rows[1]["ID da Subtarefa"], "1")
        self.assertEqual(rows[1]["Descrição"], "Executar atividade")

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
