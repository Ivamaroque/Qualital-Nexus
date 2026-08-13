import logging
import re
from functools import lru_cache
from typing import Any

from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_RULE_FIELDS = "id,nome,descricao,ordem,escopo,padrao_regex,tipo_tarefa,categoria,exemplo_entrada,exemplo_saida_json"
_MAX_RULE_TEXT_LENGTH = 12_000
_CATEGORY_ALIASES = {
    "atividade_tabela": {"atividade_tabela_2", "atividade_anomalia"},
    "anexo_documento": {"anexo"},
}


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
    def escopo_compativel(escopo_regra: Any) -> bool:
        return bool(
            escopo_regra in {"geral", escopo}
            or (escopo_regra == "anexo" and str(escopo).startswith("anexo_"))
        )

    compativeis = [
        regra
        for regra in regras
        if escopo_compativel(regra.get("escopo"))
        and (
            regra.get("escopo") in {escopo, "anexo"}
            or regra.get("categoria") in {None, "", "geral", categoria}
        )
    ]

    def prioridade_categoria(regra: dict[str, Any]) -> int:
        categoria_regra = regra.get("categoria")
        if categoria_regra == categoria:
            return 0
        if categoria_regra in {None, "", "geral"}:
            return 1
        return 2

    return sorted(
        compativeis,
        key=lambda regra: (prioridade_categoria(regra), regra.get("ordem") or 0),
    )


def preparar_blocos_para_ia(blocos: list[dict[str, Any]], regras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocos_preparados: list[dict[str, Any]] = []

    for bloco in blocos:
        regras_compativeis = filtrar_regras_por_bloco(regras, bloco["escopo"], bloco["categoria"])
        regras_correspondentes = [
            regra
            for regra in regras_compativeis
            if _categoria_corresponde(regra.get("categoria"), bloco["categoria"])
            and _regra_corresponde_ao_bloco(regra, bloco["texto"])
        ]
        regras_da_categoria = [
            regra
            for regra in regras_compativeis
            if _regra_corresponde_categoria(regra.get("categoria"), bloco["categoria"])
            and regra.get("tipo_tarefa") != "Ignorar"
        ]
        regra_principal = (regras_correspondentes or regras_da_categoria or [None])[0]
        blocos_preparados.append(
            {
                **bloco,
                "orientacao_parser": {
                    "regra": regra_principal.get("nome") if regra_principal else None,
                    "regraId": regra_principal.get("id") if regra_principal else None,
                    "tipoTarefa": regra_principal.get("tipo_tarefa") if regra_principal else None,
                    "acao": "ignorar" if regra_principal and regra_principal.get("tipo_tarefa") == "Ignorar" else "converter",
                },
            }
        )

    return blocos_preparados


def _categoria_corresponde(categoria_regra: Any, categoria_bloco: str) -> bool:
    if categoria_regra in {None, "", "geral", categoria_bloco}:
        return True
    return categoria_regra in _CATEGORY_ALIASES.get(categoria_bloco, set())


def _regra_corresponde_categoria(categoria_regra: Any, categoria_bloco: str) -> bool:
    return categoria_regra == categoria_bloco or categoria_regra in _CATEGORY_ALIASES.get(categoria_bloco, set())


def _regra_corresponde_ao_bloco(regra: dict[str, Any], texto: str) -> bool:
    padrao = regra.get("padrao_regex")
    if not isinstance(padrao, str) or not padrao.strip():
        return False
    regex = _compilar_regex(padrao)
    return regex.search(texto[:_MAX_RULE_TEXT_LENGTH]) is not None if regex else False


@lru_cache(maxsize=512)
def _compilar_regex(padrao: str) -> re.Pattern[str] | None:
    try:
        return re.compile(padrao)
    except re.error:
        return None
