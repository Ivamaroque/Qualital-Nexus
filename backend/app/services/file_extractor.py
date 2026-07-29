import logging

import fitz  # PyMuPDF
from fastapi import HTTPException, UploadFile, status

from app.core.config import Settings
from app.models.schemas import ExtractedDocument
from app.services.markdown_converter import text_to_markdown

logger = logging.getLogger(__name__)


async def extract_pdf_file(file: UploadFile, file_order: int, settings: Settings) -> ExtractedDocument:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="São aceitos apenas arquivos PDF.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"O arquivo {file.filename} está vazio.")
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"O arquivo {file.filename} excede o limite de {settings.max_file_size_mb} MB.",
        )
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"O arquivo {file.filename} não é um PDF válido.")

    try:
        document = fitz.open(stream=content, filetype="pdf")
        text = "\n\n".join(page.get_text("text", sort=True) for page in document)
        document.close()
    except (fitz.FileDataError, RuntimeError) as exc:
        logger.info("Falha ao abrir PDF filename=%s", file.filename)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Não foi possível ler {file.filename}.") from exc

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"O PDF {file.filename} não possui texto selecionável. OCR ainda não está disponível.",
        )

    logger.info("Texto extraído filename=%s ordem=%d caracteres=%d", file.filename, file_order, len(text))
    return ExtractedDocument(file_order=file_order, filename=file.filename, markdown=text_to_markdown(text))
