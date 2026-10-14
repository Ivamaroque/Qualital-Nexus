import logging

from fastapi import HTTPException, UploadFile, status

from app.core.config import Settings
from app.models.schemas import ParsedBlock
from app.services.ai_service import normalize_complex_blocks
from app.services.file_extractor import extract_document_file
from app.services.parser_rules import parse_document

logger = logging.getLogger(__name__)


async def process_extraction(files: list[UploadFile], settings: Settings) -> list[ParsedBlock]:
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Envie ao menos um documento no campo files.")
    if len(files) > settings.max_files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"O limite é de {settings.max_files} arquivos por envio.")

    all_blocks: list[ParsedBlock] = []
    # O enumerate mantém a sequência original de partes multipart do frontend.
    for file_order, file in enumerate(files, start=1):
        document = await extract_document_file(file, file_order, settings)
        blocks = parse_document(document)
        all_blocks.extend(await normalize_complex_blocks(blocks, settings))
        logger.info("Arquivo processado filename=%s ordem=%d blocos=%d", document.filename, file_order, len(blocks))
    return all_blocks
