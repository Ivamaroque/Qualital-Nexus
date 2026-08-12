import logging

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.models.schemas import ExtractedDocument
from app.services.document_service import extrair_texto_documento
from app.services.markdown_converter import text_to_markdown

logger = logging.getLogger(__name__)


async def extract_document_file(file: UploadFile, file_order: int, settings: Settings) -> ExtractedDocument:
    filename = file.filename or f"arquivo_{file_order}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"O arquivo {file.filename} está vazio.")
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"O arquivo {file.filename} excede o limite de {settings.max_file_size_mb} MB.",
        )
    try:
        text = await run_in_threadpool(extrair_texto_documento, content, filename)
    except ValueError as exc:
        logger.info("Falha ao abrir documento filename=%s", filename)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Não foi possível ler {filename}: {exc}",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"O documento {filename} não possui texto extraível. OCR ainda não está disponível.",
        )

    logger.info("Texto extraído filename=%s ordem=%d caracteres=%d", file.filename, file_order, len(text))
    return ExtractedDocument(file_order=file_order, filename=filename, markdown=text_to_markdown(text))
