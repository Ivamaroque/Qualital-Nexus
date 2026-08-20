from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel


class BlockType(StrEnum):
    TITULO = "Título"
    SUBTITULO = "Subtítulo"
    EXECUCAO = "Execução"
    INFORMACAO = "Informação"


@dataclass
class ExtractedDocument:
    file_order: int
    filename: str
    markdown: str


@dataclass
class ParsedBlock:
    file_order: int
    filename: str
    document_type: str
    block_order: int
    block_type: BlockType
    content: str
    section: str = ""
    hierarchy: str = ""
    needs_ai: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "qualital-nexus-backend"
    environment: str
    authentication_configured: bool
    openrouter_configured: bool
