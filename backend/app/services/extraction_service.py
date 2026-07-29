import logging

from fastapi import HTTPException, UploadFile, status

from app.core.config import Settings
from app.models.schemas import ParsedBlock
from app.services.ai_service import normalize_complex_blocks
from app.services.file_extractor import extract_pdf_file
from app.services.parser_rules import parse_document
from app.services.rag_examples import fetch_rag_examples

logger = logging.getLogger(__name__)


async def process_extraction(files: list[UploadFile], settings: Settings) -> list[ParsedBlock]:
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Envie ao menos um arquivo PDF no campo files.")
    if len(files) > settings.max_files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"O limite é de {settings.max_files} arquivos por envio.")

    all_blocks: list[ParsedBlock] = []
    examples_by_document_type: dict[str, list[dict]] = {}
    # O enumerate mantém a sequência original de partes multipart do frontend.
    for file_order, file in enumerate(files, start=1):
        document = await extract_pdf_file(file, file_order, settings)
        blocks = parse_document(document)
        document_type = blocks[0].document_type if blocks else "Desconhecido"
        if document_type not in examples_by_document_type:
            examples_by_document_type[document_type] = await fetch_rag_examples(settings, document_type)
        examples = examples_by_document_type[document_type]
        all_blocks.extend(await normalize_complex_blocks(blocks, examples, settings))
        logger.info("Arquivo processado filename=%s ordem=%d blocos=%d", document.filename, file_order, len(blocks))
    return all_blocks
