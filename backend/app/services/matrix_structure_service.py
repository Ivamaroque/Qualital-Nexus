import re
from collections import defaultdict
from typing import Any

from app.utils.text_utils import normalized_for_match


_NUMERIC_HTA_RE = re.compile(r"^\d+(?:\.\d+)*\.$")
_ANEXO_ITEM_RE = re.compile(r"^ANEXO\s+[A-Z]\d*\s*-\s*", re.IGNORECASE)
_DOCUMENT_LIST_HEADING_RE = re.compile(
    r"\b(?:LISTA\s+DE\s+|SEGUINTES\s+)?(?:DOCUMENTOS|REFERENCIAS)"
    r"(?:\s+(?:DE\s+)?[A-Z0-9 ]+)?$"
)
_GENERIC_CONTAINER_TITLES = {
    "ATIVIDADE",
    "DESCRICAO",
    "DETALHAMENTO DAS ATIVIDADES DO PROCESSO",
    "ETAPAS DE EXECUCAO DAS TAREFAS",
    "PROCEDIMENTO",
}


def _item_normalizado(valor: Any) -> str:
    return str(valor or "").strip().rstrip(".")


def _item_para_hierarquia(valor: Any) -> str:
    return _ANEXO_ITEM_RE.sub("", _item_normalizado(valor)).rstrip(".")


def _descricao_tarefa_com_item(descricao: str, item: str) -> str:
    texto = " ".join(str(descricao or "").split()).strip()
    item_exibicao = str(item or "").strip()
    item_normalizado = _item_normalizado(item_exibicao)
    if not texto or not item_normalizado or re.search(
        rf"\({re.escape(item_normalizado)}\.?\)\s*$",
        texto,
    ):
        return texto
    return f"{texto.rstrip()} ({item_exibicao})"


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


def _aplicar_hierarquia_do_anexo_standalone(
    blocos_por_ordem: dict[int, dict[str, Any]],
    resultado: list[dict[str, Any]],
    titulos_por_item: dict[str, dict[str, Any]],
    raiz_inicial: int,
) -> None:
    """Numera anexos em arquivos próprios sem misturar seus itens com o documento principal."""
    ordens_standalone = {
        ordem
        for ordem, bloco in blocos_por_ordem.items()
        if bloco.get("anexoStandalone")
    }
    if not ordens_standalone:
        return

    for linha in resultado:
        if linha.get("ordemBloco") in ordens_standalone and linha.get("tipoTarefa") == "Padrão/Anexo":
            linha["subtarefaHTA"] = f"{raiz_inicial}."
            if not linha.get("descricaoTarefa"):
                linha["descricaoTarefa"] = _descricao_tarefa_com_item(
                    str(linha.get("descricao") or ""),
                    str(linha.get("itemPadrao") or ""),
                )
            break

    grupos: list[str] = []
    for linha in resultado:
        ordem = linha.get("ordemBloco")
        bloco = blocos_por_ordem.get(int(ordem)) if str(ordem or "").isdigit() else None
        if not bloco or not bloco.get("anexoStandalone") or linha.get("tipoTarefa") != "Execução":
            continue
        grupo = _item_para_hierarquia(bloco.get("secaoContextual"))
        if grupo and grupo not in grupos:
            grupos.append(grupo)
    if not grupos:
        return

    def grupo_superior(grupo: str) -> str:
        partes = grupo.split(".")
        return ".".join(partes[:2]) if len(partes) >= 2 else grupo

    superiores: list[str] = []
    subgrupos: defaultdict[str, list[str]] = defaultdict(list)
    for grupo in grupos:
        superior = grupo_superior(grupo)
        if superior not in superiores:
            superiores.append(superior)
        if grupo != superior and grupo not in subgrupos[superior]:
            subgrupos[superior].append(grupo)

    prefixos: dict[str, str] = {}
    for indice_superior, superior in enumerate(superiores, start=1):
        prefixos[superior] = f"{raiz_inicial}.{indice_superior}"
        titulo_superior = titulos_por_item.get(superior)
        if titulo_superior:
            titulo_superior["subtarefaHTA"] = f"{prefixos[superior]}."
            titulo_superior["descricaoTarefa"] = _descricao_tarefa_com_item(
                str(titulo_superior.get("descricao") or ""),
                str(titulo_superior.get("itemPadrao") or superior),
            )
        for indice_subgrupo, subgrupo in enumerate(subgrupos[superior], start=1):
            prefixos[subgrupo] = f"{prefixos[superior]}.{indice_subgrupo}"
            titulo_subgrupo = titulos_por_item.get(subgrupo)
            if titulo_subgrupo:
                titulo_subgrupo["subtarefaHTA"] = f"{prefixos[subgrupo]}."
                titulo_subgrupo["descricaoTarefa"] = _descricao_tarefa_com_item(
                    str(titulo_subgrupo.get("descricao") or ""),
                    str(titulo_subgrupo.get("itemPadrao") or subgrupo),
                )

    contadores: defaultdict[str, int] = defaultdict(int)
    for linha in resultado:
        ordem = linha.get("ordemBloco")
        bloco = blocos_por_ordem.get(int(ordem)) if str(ordem or "").isdigit() else None
        if not bloco or not bloco.get("anexoStandalone") or linha.get("tipoTarefa") != "Execução":
            continue
        grupo = _item_para_hierarquia(bloco.get("secaoContextual"))
        prefixo = prefixos.get(grupo) or prefixos.get(grupo_superior(grupo))
        if not prefixo:
            continue
        contadores[grupo] += 1
        linha["subtarefaHTA"] = f"{prefixo}.{contadores[grupo]}."
        linha["descricaoTarefa"] = _descricao_tarefa_com_item(
            str(linha.get("descricaoTarefa") or ""),
            str(linha.get("itemPadrao") or ""),
        )


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
        if (
            ordem not in ordens_com_execucao
            or bloco.get("anexoStandalone")
            or not str(bloco.get("escopo") or "").startswith("anexo_")
        ):
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
        if (
            not bloco
            or bloco.get("anexoStandalone")
            or not str(bloco.get("escopo") or "").startswith("anexo_")
        ):
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

    titulos_operacionais_por_grupo: dict[str, dict[str, Any]] = {}
    for linha in resultado:
        ordem = linha.get("ordemBloco")
        bloco = blocos_por_ordem.get(int(ordem)) if str(ordem or "").isdigit() else None
        if not bloco or linha.get("tipoTarefa") != "Título/Subtítulo":
            continue
        if bloco.get("categoria") != "etapa_operacional" or int(bloco.get("etapaOperacional") or 0) <= 1:
            continue
        grupo = (
            f"__etapa_{int(bloco['etapaOperacional'])}_"
            f"{_item_para_hierarquia(bloco.get('secaoContextual'))}"
        )
        secao_fonte = str(bloco.get("secaoContextual") or "").strip().rstrip(".")
        if secao_fonte:
            linha["itemPadrao"] = f"{secao_fonte}."
        titulos_operacionais_por_grupo[grupo] = linha

    _aplicar_hierarquia_do_anexo_standalone(
        blocos_por_ordem,
        resultado,
        titulos_por_item,
        raiz_inicial,
    )

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
        item_exibicao = str(
            linha.get("itemPadrao")
            or contexto.get("itemPadrao")
            or bloco.get("itemPadraoDetectado")
            or bloco.get("secaoContextual")
            or ""
        ).strip()
        item = _item_normalizado(item_exibicao)
        linha["itemPadrao"] = item_exibicao

        hta_atual = str(linha.get("subtarefaHTA") or "").strip()
        if _NUMERIC_HTA_RE.fullmatch(hta_atual):
            linha["descricaoTarefa"] = _descricao_tarefa_com_item(
                str(linha.get("descricaoTarefa") or ""),
                item_exibicao,
            )
            continue

        grupo_operacional = _item_para_hierarquia(contexto.get("grupoOperacional"))
        secao = grupo_operacional or _item_para_hierarquia(bloco.get("secaoContextual") or item)
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
            titulo_raiz = titulos_por_item.get(raiz) or titulos_operacionais_por_grupo.get(raiz)
            if titulo_raiz:
                titulo_raiz["subtarefaHTA"] = f"{numero_raiz[raiz]}."
                descricao_titulo = str(titulo_raiz.get("descricao") or "")
                if raiz.startswith("__etapa_"):
                    descricao_titulo = re.sub(
                        r"^ETAPA\s+\d+\s*[-–—:]\s*",
                        "",
                        descricao_titulo,
                        flags=re.IGNORECASE,
                    ).strip()
                titulo_raiz["descricaoTarefa"] = _descricao_tarefa_com_item(
                    descricao_titulo,
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
        linha["descricaoTarefa"] = _descricao_tarefa_com_item(
            str(linha.get("descricaoTarefa") or ""),
            item_exibicao,
        )

    return resultado
