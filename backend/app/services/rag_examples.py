import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def fetch_rag_examples(settings: Settings, document_type: str) -> list[dict[str, Any]]:
    """Busca exemplos no Supabase quando ele estiver configurado.

    A tabela é propositalmente configurável. Espera colunas compatíveis com
    ``document_type``, ``input_text`` e ``expected_type``; falhas de RAG não
    interrompem a extração baseada em regras.
    """
    if not settings.supabase_is_configured:
        return []

    base_url = settings.supabase_url.rstrip("/")
    if base_url.endswith("/rest/v1"):
        rest_url = base_url
    else:
        rest_url = f"{base_url}/rest/v1"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                f"{rest_url}/{settings.rag_examples_table}",
                params={"document_type": f"eq.{document_type}", "limit": str(settings.rag_examples_limit)},
                headers={"apikey": settings.supabase_anon_key or "", "Authorization": f"Bearer {settings.supabase_anon_key}"},
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else []
    except httpx.HTTPError:
        logger.warning("Consulta RAG indisponível para tipo=%s; seguindo sem exemplos.", document_type, exc_info=True)
        return []
