import re
from collections import defaultdict
from typing import Any

from app.utils.text_utils import normalized_for_match


_NUMERIC_HTA_RE = re.compile(r"^\d+(?:\.\d+)*\.$")
_ANEXO_ITEM_RE = re.compile(r"^ANEXO\s+[A-Z]\s*-\s*", re.IGNORECASE)
_DOCUMENT_LIST_HEADING_RE = re.compile(
    r"\b(?:LISTA\s+DE\s+|SEGUINTES\s+)?(?:DOCUMENTOS|REFERENCIAS)"
    r"(?:\s+(?:DE\s+)?[A-Z0-9 ]+)?$"
)
_GENERIC_CONTAINER_TITLES = {
    "ATIVIDADE",
    "DESCRICAO",
    "ETAPAS DE EXECUCAO DAS TAREFAS",
    "PROCEDIMENTO",
}


def _item_normalizado(valor: Any) -> str:
    return str(valor or "").strip().rstrip(".")


def _item_para_hierarquia(valor: Any) -> str:
    return _ANEXO_ITEM_RE.sub("", _item_normalizado(valor)).rstrip(".")


def _descricao_tarefa_com_item(descricao: str, item: str) -> str:
    texto = " ".join(str(descricao or "").split()).strip()
    item = _item_normalizado(item)
    if not texto or not item or re.search(rf"\({re.escape(item)}\.?\)\s*$", texto):
        return texto
    return f"{texto.rstrip()} ({item})"


def _ancestral_operacional(
    secao: str,
    titulos_por_item: dict[str, dict[str, Any]],
) -> str:
    secao = _item_normalizado(secao)
    partes = secao.split(".") if secao else []
    if len(partes) < 3:
        return secao
    pai = ".".join(partes[:-1])
    titulo_pai = titulos_por_item.get(pai)
    if not titulo_pai:
        return secao
    descricao_pai = re.sub(
        r"^[^A-Z0-9]+",
        "",
        normalized_for_match(str(titulo_pai.get("descricao") or "")),
    )
    if descricao_pai in _GENERIC_CONTAINER_TITLES:
        return secao
    return pai


def _consolidar_continuacoes_informativas(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    consolidadas: list[dict[str, Any]] = []
    for linha_original in linhas:
        linha = dict(linha_original)
        if consolidadas:
            anterior = consolidadas[-1]
            descricao_anterior = normalized_for_match(str(anterior.get("descricao") or ""))
            descricao_atual = str(linha.get("descricao") or "").strip()
            if (
                anterior.get("tipoTarefa") == "Informação"
                and linha.get("tipoTarefa") == "Informação"
                and _DOCUMENT_LIST_HEADING_RE.search(descricao_anterior)
                and descricao_atual.startswith(("•", "-"))
            ):
                anterior["descricao"] = f"{str(anterior.get('descricao') or '').rstrip()}\n{descricao_atual}"
                continue
        consolidadas.append(linha)
    return consolidadas


def _sufixo_local_do_grupo(item: str, grupo: str) -> str:
    correspondencia = re.fullmatch(
        rf"{re.escape(grupo.rstrip('.'))}\.?(?:\((\d+(?:\.\d+)*)\.?\))",
        item.rstrip("."),
    )
    if correspondencia:
        return correspondencia.group(1)
    grupo_sem_ponto = grupo.rstrip(".")
    if item.startswith(f"{grupo_sem_ponto}."):
        return item.removeprefix(f"{grupo_sem_ponto}.").rstrip(".")
    return ""


def _aplicar_hierarquia_do_anexo(
    blocos_por_ordem: dict[int, dict[str, Any]],
    resultado: list[dict[str, Any]],
    titulos_por_item: dict[str, dict[str, Any]],
    raiz_inicial: int,
) -> None:
    """Mantém todo o anexo em uma raiz HTA e respeita listas locais do Word."""
    ordens_com_execucao = {
        int(linha["ordemBloco"])
        for linha in resultado
        if linha.get("tipoTarefa") == "Execução" and str(linha.get("ordemBloco") or "").isdigit()
    }
    grupos: list[str] = []
    for ordem, bloco in blocos_por_ordem.items():
        if ordem not in ordens_com_execucao or not str(bloco.get("escopo") or "").startswith("anexo_"):
            continue
        grupo = _item_para_hierarquia(bloco.get("secaoContextual"))
        if grupo and grupo not in grupos:
            grupos.append(grupo)
    if not grupos:
        return

    prefixos: dict[str, str] = {}
    contador_primario = 0
    contador_posterior = 1
    fase_primaria = True
    ultimo_prefixo_primario = ""
    bases_primarias: dict[str, str] = {}

    for grupo in grupos:
        primeiro = grupo.split(".", maxsplit=1)[0]
        if fase_primaria and primeiro == "2":
            fase_primaria = False
        if fase_primaria:
            if primeiro == "1":
                ancestrais = [
                    item
                    for item in titulos_por_item
                    if len(item.split(".")) >= 3 and grupo.startswith(f"{item}.")
                ]
                base = max(ancestrais, key=len, default=grupo)
                if base not in bases_primarias:
                    contador_primario += 1
                    bases_primarias[base] = f"{raiz_inicial}.1.{contador_primario}"
                prefixo_base = bases_primarias[base]
                sufixo = grupo.removeprefix(base).lstrip(".")
                prefixos[grupo] = f"{prefixo_base}.{sufixo}" if sufixo else prefixo_base
                ultimo_prefixo_primario = prefixos[grupo]
            elif re.fullmatch(r"\d+[A-Z]", grupo, re.IGNORECASE):
                contador_primario += 1
                ultimo_prefixo_primario = f"{raiz_inicial}.1.{contador_primario}"
                prefixos[grupo] = ultimo_prefixo_primario
            elif ultimo_prefixo_primario:
                prefixos[grupo] = ultimo_prefixo_primario
        else:
            contador_posterior += 1
            prefixos[grupo] = f"{raiz_inicial}.{contador_posterior}"

    contadores: defaultdict[str, int] = defaultdict(int)
    htas_usadas: set[str] = set()
    for linha in resultado:
        ordem = linha.get("ordemBloco")
        bloco = blocos_por_ordem.get(int(ordem)) if str(ordem or "").isdigit() else None
        if not bloco or not str(bloco.get("escopo") or "").startswith("anexo_"):
            continue
        grupo = _item_para_hierarquia(bloco.get("secaoContextual"))
        prefixo = prefixos.get(grupo)
        if not prefixo:
            continue
        item = _item_para_hierarquia(linha.get("itemPadrao"))
        sufixo = _sufixo_local_do_grupo(item, grupo)
        if linha.get("tipoTarefa") == "Título/Subtítulo":
            hta = f"{prefixo}.{sufixo}." if sufixo else f"{prefixo}."
            linha["subtarefaHTA"] = re.sub(r"\.{2,}", ".", hta)
            linha["descricaoTarefa"] = _descricao_tarefa_com_item(
                str(linha.get("descricao") or ""),
                str(linha.get("itemPadrao") or ""),
            )
            continue
        if linha.get("tipoTarefa") != "Execução":
            continue
        if sufixo:
            primeiro_nivel = sufixo.split(".", maxsplit=1)[0]
            if primeiro_nivel.isdigit():
                contadores[grupo] = max(contadores[grupo], int(primeiro_nivel))
        candidato = re.sub(r"\.{2,}", ".", f"{prefixo}.{sufixo}.") if sufixo else ""
        if not sufixo or candidato in htas_usadas:
            contadores[grupo] += 1
            sufixo = str(contadores[grupo])
        linha["subtarefaHTA"] = re.sub(r"\.{2,}", ".", f"{prefixo}.{sufixo}.")
        htas_usadas.add(linha["subtarefaHTA"])
        linha["descricaoTarefa"] = _descricao_tarefa_com_item(
            str(linha.get("descricaoTarefa") or ""),
            str(linha.get("itemPadrao") or ""),
        )


def consolidar_hierarquia_tarefas(
    blocos: list[dict[str, Any]],
    linhas: list[dict[str, Any]],
    raiz_inicial: int = 1,
) -> list[dict[str, Any]]:
    """Atribui HTA numérica global depois que todos os lotes do arquivo foram reunidos."""
    blocos_por_ordem = {int(bloco["ordem"]): bloco for bloco in blocos}
    resultado = _consolidar_continuacoes_informativas(linhas)
    titulos_por_item: dict[str, dict[str, Any]] = {}
    for linha in resultado:
        item = _item_para_hierarquia(linha.get("itemPadrao"))
        if item and linha.get("tipoTarefa") == "Título/Subtítulo":
            titulos_por_item[item] = linha

    _aplicar_hierarquia_do_anexo(
        blocos_por_ordem,
        resultado,
        titulos_por_item,
        raiz_inicial,
    )

    raizes_existentes = [
        int(str(linha.get("subtarefaHTA")).strip().rstrip("."))
        for linha in resultado
        if linha.get("tipoTarefa") == "Título/Subtítulo"
        and re.fullmatch(r"\d+\.", str(linha.get("subtarefaHTA") or "").strip())
    ]
    proxima_raiz = max([max(1, raiz_inicial) - 1, *raizes_existentes]) + 1
    numero_raiz: dict[str, int] = {}
    numero_subsecao: dict[tuple[str, str], int] = {}
    contador_subsecao: defaultdict[str, int] = defaultdict(int)
    contador_acao: defaultdict[tuple[str, str], int] = defaultdict(int)

    for linha in resultado:
        if linha.get("tipoTarefa") != "Execução":
            continue
        ordem = linha.get("ordemBloco")
        bloco = (
            blocos_por_ordem.get(int(ordem))
            if isinstance(ordem, int) or str(ordem).isdigit()
            else None
        )
        if not bloco:
            continue

        contexto = bloco.get("contextoTarefa") or {}
        item = _item_normalizado(
            linha.get("itemPadrao")
            or contexto.get("itemPadrao")
            or bloco.get("itemPadraoDetectado")
            or bloco.get("secaoContextual")
        )
        linha["itemPadrao"] = item

        hta_atual = str(linha.get("subtarefaHTA") or "").strip()
        if _NUMERIC_HTA_RE.fullmatch(hta_atual):
            linha["descricaoTarefa"] = _descricao_tarefa_com_item(str(linha.get("descricaoTarefa") or ""), item)
            continue

        secao = _item_para_hierarquia(bloco.get("secaoContextual") or item)
        # Tarefas sem numeração/contexto não podem compartilhar uma HTA por acidente.
        raiz = (
            _ancestral_operacional(secao, titulos_por_item)
            or secao
            or item
            or f"__bloco_{ordem}"
        )
        if raiz not in numero_raiz:
            numero_raiz[raiz] = proxima_raiz
            proxima_raiz += 1
            titulo_raiz = titulos_por_item.get(raiz)
            if titulo_raiz:
                titulo_raiz["subtarefaHTA"] = f"{numero_raiz[raiz]}."
                titulo_raiz["descricaoTarefa"] = _descricao_tarefa_com_item(
                    str(titulo_raiz.get("descricao") or ""),
                    str(titulo_raiz.get("itemPadrao") or raiz),
                )

        prefixo = f"{numero_raiz[raiz]}."
        subsecao = secao if secao and secao != raiz and secao.startswith(f"{raiz}.") else ""
        if subsecao:
            chave_subsecao = (raiz, subsecao)
            if chave_subsecao not in numero_subsecao:
                contador_subsecao[raiz] += 1
                numero_subsecao[chave_subsecao] = contador_subsecao[raiz]
                titulo_subsecao = titulos_por_item.get(subsecao)
                if titulo_subsecao:
                    titulo_subsecao["subtarefaHTA"] = (
                        f"{numero_raiz[raiz]}."
                        f"{numero_subsecao[chave_subsecao]}."
                    )
                    titulo_subsecao["descricaoTarefa"] = _descricao_tarefa_com_item(
                        str(titulo_subsecao.get("descricao") or ""),
                        str(titulo_subsecao.get("itemPadrao") or subsecao),
                    )
            prefixo = f"{numero_raiz[raiz]}.{numero_subsecao[chave_subsecao]}."

        chave_contador = (raiz, subsecao)
        contador_acao[chave_contador] += 1
        linha["subtarefaHTA"] = f"{prefixo}{contador_acao[chave_contador]}."
        linha["descricaoTarefa"] = _descricao_tarefa_com_item(str(linha.get("descricaoTarefa") or ""), item)

    return resultado
