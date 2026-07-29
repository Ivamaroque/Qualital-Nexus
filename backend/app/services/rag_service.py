import logging
from typing import Any

from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def buscar_exemplos_rag(
    texto: str,
    categoria: str | None,
    palavras_chave: list[str],
    limite: int = 2,
) -> list[dict[str, Any]]:
    client = get_supabase_client()
    if client is None:
        return []
    try:
        response = client.rpc(
            "buscar_exemplos_rag",
            {
                "p_texto": texto,
                "p_categoria": categoria,
                "p_palavras_chave": palavras_chave,
                "p_limite": limite,
            },
        ).execute()
        return response.data if isinstance(response.data, list) else []
    except Exception:
        logger.exception("Consulta RAG indisponível categoria=%s; seguindo sem exemplos.", categoria)
        return []
