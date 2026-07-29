import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import BlockType, ExtractedDocument
from app.services.csv_generator import generate_csv
from app.services.parser_rules import parse_document


class ParserRulesTest(unittest.TestCase):
    def test_pe_maps_table_columns_to_execution_and_information(self):
        document = ExtractedDocument(
            file_order=1,
            filename="pe.pdf",
            markdown="1. OBJETIVO\nOrientar o processo.\nCOMO FAZER\nRegistrar a atividade.\nPORQUE FAZER\nGarantir rastreabilidade.",
        )

        blocks = parse_document(document)

        self.assertEqual(blocks[0].block_type, BlockType.TITULO)
        self.assertEqual(blocks[1].block_type, BlockType.INFORMACAO)
        self.assertEqual(blocks[2].block_type, BlockType.EXECUCAO)
        self.assertEqual(blocks[3].block_type, BlockType.INFORMACAO)

    def test_annex_b_keeps_hierarchy_and_classifies_notice(self):
        document = ExtractedDocument(
            file_order=2,
            filename="anexo-b.pdf",
            markdown="ANEXO B\n1. Processo\n1.1. Preparação\n1.1.1. Conferência\n1.1.1.1 Registrar evidência\nATENÇÃO: não pular etapas.",
        )

        blocks = parse_document(document)

        self.assertEqual(blocks[1].block_type, BlockType.TITULO)
        self.assertEqual(blocks[2].block_type, BlockType.TITULO)
        self.assertEqual(blocks[4].block_type, BlockType.EXECUCAO)
        self.assertEqual(blocks[4].hierarchy, "1.1.1.1")
        self.assertEqual(blocks[5].block_type, BlockType.INFORMACAO)

    def test_annex_a_never_marks_rows_as_execution(self):
        document = ExtractedDocument(
            file_order=3,
            filename="anexo-a.pdf",
            markdown="ANEXO A\nCódigo | Descrição\nA-01 | Referência operacional",
        )

        blocks = parse_document(document)

        self.assertTrue(all(block.block_type == BlockType.INFORMACAO for block in blocks))
        self.assertIn("ordem_arquivo", generate_csv(blocks).decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
