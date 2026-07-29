import logging
from typing import Any

from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_RULE_FIELDS = "id,nome,descricao,ordem,escopo,padrao_regex,tipo_tarefa,categoria,exemplo_entrada,exemplo_saida_json"


def buscar_parser_rules() -> list[dict[str, Any]]:
    client = get_supabase_client()
    if client is None:
        logger.warning("Supabase não configurado; processamento seguirá sem regras remotas.")
        return []
    try:
        response = client.table("parser_rules").select(_RULE_FIELDS).eq("ativo", True).order("ordem").execute()
        return response.data if isinstance(response.data, list) else []
    except Exception:
        logger.exception("Falha segura ao buscar parser_rules.")
        return []


def filtrar_regras_por_bloco(regras: list[dict[str, Any]], escopo: str, categoria: str) -> list[dict[str, Any]]:
    compativeis = [regra for regra in regras if regra.get("escopo") in {"geral", escopo}]
    return sorted(
        compativeis,
        key=lambda regra: (0 if regra.get("categoria") == categoria else 1, regra.get("ordem") or 0),
    )
