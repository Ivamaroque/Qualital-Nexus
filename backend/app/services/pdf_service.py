"""Fachada compatível para extração e interpretação de documentos PDF.

Os detalhes de PyMuPDF ficam em ``pdf_extraction_service``; as regras textuais,
em ``pdf_text_service``; e a montagem dos blocos, em ``pdf_block_service``.
Os símbolos continuam exportados aqui para preservar os consumidores
existentes.
"""

from app.services.pdf_extraction_service import (
    _serializar_tabela,
    extrair_texto_e_imagens_pdf,
)
from app.services.pdf_block_service import separar_blocos
from app.services.pdf_text_service import detectar_categoria, limpar_texto_pdf

__all__ = [
    "_serializar_tabela",
    "detectar_categoria",
    "extrair_texto_e_imagens_pdf",
    "limpar_texto_pdf",
    "separar_blocos",
]
