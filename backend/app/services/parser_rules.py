import re

from app.models.schemas import BlockType, ExtractedDocument, ParsedBlock
from app.utils.text_utils import item_hierarchy, normalized_for_match, remove_item_number

PE_SECTION_RE = re.compile(r"^(\d+)\.\s*(OBJETIVO|APLICAÇÃO|DESCRIÇÃO|REGISTROS|DEFINIÇÕES)\b", re.IGNORECASE)
ANNEX_A_RE = re.compile(r"\bANEXO\s+A\b", re.IGNORECASE)
ANNEX_B_RE = re.compile(r"\bANEXO\s+B\b", re.IGNORECASE)
NOTICE_PREFIXES = ("OBS", "OBSERVACAO", "ATENCAO", "LEMBRE-SE", "LEMBRE SE")


def detect_document_type(markdown: str) -> str:
    head = markdown[:4000]
    if ANNEX_A_RE.search(head):
        return "Anexo A"
    if ANNEX_B_RE.search(head):
        return "Anexo B"
    if PE_SECTION_RE.search(head):
        return "PE"
    return "Desconhecido"


def parse_document(document: ExtractedDocument) -> list[ParsedBlock]:
    document_type = detect_document_type(document.markdown)
    lines = [line.removeprefix("## ").strip() for line in document.markdown.splitlines() if line.strip()]
    if document_type == "PE":
        return _parse_pe(document, lines)
    if document_type == "Anexo B":
        return _parse_annex_b(document, lines)
    if document_type == "Anexo A":
        return _parse_annex_a(document, lines)
    return _parse_generic(document, lines, document_type)


def _new_block(document: ExtractedDocument, document_type: str, block_order: int, block_type: BlockType, content: str, section: str = "", hierarchy: str = "", needs_ai: bool = False) -> ParsedBlock:
    return ParsedBlock(document.file_order, document.filename, document_type, block_order, block_type, content, section, hierarchy, needs_ai)


def _parse_pe(document: ExtractedDocument, lines: list[str]) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    section = ""
    table_mode: BlockType | None = None
    for line in lines:
        section_match = PE_SECTION_RE.match(line)
        if section_match:
            section = line
            table_mode = None
            blocks.append(_new_block(document, "PE", len(blocks) + 1, BlockType.TITULO, line, section))
            continue
        normalized = normalized_for_match(line)
        if "COMO FAZER" in normalized:
            table_mode = BlockType.EXECUCAO
            continue
        if "PORQUE FAZER" in normalized:
            table_mode = BlockType.INFORMACAO
            continue
        if not line or len(line) < 3:
            continue
        block_type = table_mode or BlockType.INFORMACAO
        blocks.append(_new_block(document, "PE", len(blocks) + 1, block_type, line, section, needs_ai=not section and len(line) > 300))
    return blocks


def _parse_annex_b(document: ExtractedDocument, lines: list[str]) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    for line in lines:
        normalized = normalized_for_match(line)
        hierarchy = item_hierarchy(line)
        if normalized.startswith(NOTICE_PREFIXES):
            block_type = BlockType.INFORMACAO
        elif hierarchy:
            level = hierarchy.count(".") + 1
            block_type = BlockType.TITULO if level <= 2 else BlockType.SUBTITULO if level == 3 else BlockType.EXECUCAO
        else:
            block_type = BlockType.EXECUCAO
        content = remove_item_number(line) if hierarchy else line
        blocks.append(_new_block(document, "Anexo B", len(blocks) + 1, block_type, content, hierarchy=hierarchy, needs_ai=not hierarchy and len(content) > 350))
    return blocks


def _parse_annex_a(document: ExtractedDocument, lines: list[str]) -> list[ParsedBlock]:
    return [
        _new_block(document, "Anexo A", index, BlockType.INFORMACAO, line)
        for index, line in enumerate(lines, start=1)
        if len(line) >= 3
    ]


def _parse_generic(document: ExtractedDocument, lines: list[str], document_type: str) -> list[ParsedBlock]:
    return [
        _new_block(document, document_type, index, BlockType.INFORMACAO, line, needs_ai=len(line) > 350)
        for index, line in enumerate(lines, start=1)
        if len(line) >= 3
    ]
