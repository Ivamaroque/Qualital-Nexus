import re

import fitz

from app.utils.text_utils import normalize_whitespace, normalized_for_match


_PAGE_RE = re.compile(r"(?:INTERNA\s+)?página\s+\d+\s+de\s+\d+", re.IGNORECASE)
_UNDERSCORE_RE = re.compile(r"^[_\-]{3,}$")
_SECTION_RE = re.compile(r"^(?:\d+\.|\d+\.\d+(?:\.\d+){0,6}\.?)\s+(?:[-–—]\s*)?.+")
_ITEM_PADRAO_RE = re.compile(r"^\s*(\d+\.(?:\d+\.)*|\d+(?:\.\d+)+)(?=\s|[-–—]|$)")
_TABLE_RE = re.compile(r"^(?:tabela\s*\d+|quadro\s*\d+|anexo\s+[a-z])\b", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^(?:[•·▪◦*-]|\d+[.)-]|\d+\s*[-–—])\s+\S+")
_PROCESS_REFERENCE_RE = re.compile(r"^N\d+\s*[-–—]\s+", re.IGNORECASE)
_DOCUMENT_CODE_RE = re.compile(r"^(?:PE|PG|PR|PP)-[A-Z0-9]+-\d{5}\b", re.IGNORECASE)
_ANEXO_DOCUMENTO_RE = re.compile(r"^ANEXO\s+([A-Z])$", re.IGNORECASE)
_TABLE_HEADER_RE = re.compile(
    r"^(?:O QUE FAZER|EXECUTANTE|ONDE REGISTRAR|ATIVIDADE|ASPECTO/PERIGO|IMPACTO/RISCO|AÇÕES DE CONTROLE)$",
    re.IGNORECASE,
)
_TECHNICAL_MARKER_RE = re.compile(
    r"^(?:objetivo|aplicação|descrição|como fazer|porque fazer|registros|definições|recursos necessários|itens críticos)\b",
    re.IGNORECASE,
)
_MAX_BLOCK_CHARACTERS = 6_000
_MAX_GROUPED_TABLE_CHARACTERS = 3_000
_NOISE_LINE_RE = re.compile(
    r"^(?:"
    r"PROPRIEDADE\s+DA\s+PETROBRAS\s+PAGE\s+\d+\s+DE\s+NUMPAGES(?:\s+\d+)?"
    r"|LIST\s+\d+\s+\d+\s+OF\s+\d+"
    r"|SHAPE\s+\\\*\s+MERGEFORMAT"
    r"|TTONT-KM3(?:\s*\([^)]*\))?\s*[0-9,\.]*"
    r"|EMED-\d+\b.*"
    r")$",
    re.IGNORECASE,
)
_NUMBERED_ITEM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s*(?:[-–—]\s*)?(.*)$")
_ANEXO_ALPHANUMERIC_HEADING_RE = re.compile(
    r"^\s*(\d+[A-Z])\s*[-–—]\s*(.+)$",
    re.IGNORECASE,
)
_ACTION_IMPERATIVE_RE = re.compile(
    r"\b(?:acompanhe|acompanhar|abra|abrir|acione|acionar|aperte|apertar|baixe|baixar|clique|clicar|digite|digitar|"
    r"escolha|escolher|feche|fechar|informe|informar|inspecione|inspecionar|levante|levantar|"
    r"observe|observar|recoloque|recolocar|retorne|retornar|retire|retirar|suba|subir|teste|testar|"
    r"utilize|utilizar|verifique|verificar|varie|variar)\b",
    re.IGNORECASE,
)
_ANEXO_OPERATIONAL_HEADING_RE = re.compile(
    r"^\s*\d+(?:\.\d+)*\.?\s*(?:[-–—]\s*)?"
    r"(?:ACOMPANHAR|CHECAR|INSPECIONAR|VERIFICAÇÃO|VERIFICACAO)\b",
    re.IGNORECASE,
)
_SUMARIO_TITULOS = {"OBJETIVO", "APLICAÇÃO", "DESCRIÇÃO", "REGISTROS", "DEFINIÇÕES"}
_ATIVIDADE_TABELA_RE = re.compile(r"^\s*(\d+)\s*[-–—.]\s*(.+)")
_NUMBERED_LIST_ITEM_RE = re.compile(r"^\s*\d+\s*[-–—]\s+\S+")
_TECHNICAL_GROUP_HEADER_RE = re.compile(
    r"^\s*Set'?s?\s+de\s+intertravamentos?\b",
    re.IGNORECASE,
)
_TECHNICAL_PARAMETER_RE = re.compile(
    r"^\s*(?:PSHH|PSH|PSL|PSLL|LSHH|LSH|LSL|LSLL|TSHH|TSH|TSL|TSLL|LAH|LAL)-?\w*\b",
    re.IGNORECASE,
)
_ACTION_START_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)+\.?\s+)?(?:acionar|ajustar|alinhar|aplicar|atentar|atuar|avaliar|"
    r"bloquear|coletar|comunicar|confirmar|contatar|desligar|emitir|encaminhar|"
    r"entrar\s+em\s+contato|estabelecer|executar|fechar|informar|iniciar|inspecionar|instalar|"
    r"liberar|manter|medir|monitorar|operar|parar|preencher|proceder|registrar|remover|reparar|"
    r"restabelecer|retirar|seguir|sinalizar|solicitar|tomar|transportar|verificar)\b",
    re.IGNORECASE,
)
_ACTION_CUE_RE = re.compile(
    r"\b(?:dever[aá]|dever[aã]o|deve-se|recomenda-se|solicitar|bloquear|acionar|"
    r"informar\s+imediatamente|entrar\s+em\s+contato|parar\s+os?|alinhar\s+para|"
    r"estabelecer\s+(?:a\s+)?comunica[cç][aã]o|confirmar\s+que|avaliar\s+(?:o|a)|"
    r"coletar\s+(?:uma|a)|tomar\s+as\s+a[cç][oõ]es|informar\s+(?:ao|a|o)|"
    r"s[oó]\s+abrir|abrir\s+novo\s+registro)\b",
    re.IGNORECASE,
)
_NEGATIVE_ACTION_RE = re.compile(r"\bn[aã]o\s+dev(?:e|em|er[aá]|er[aã]o)\b", re.IGNORECASE)


def _linha_dentro_de_tabela(linha_bbox: tuple[float, float, float, float], tabela_bbox: tuple[float, ...]) -> bool:
    centro_x = (linha_bbox[0] + linha_bbox[2]) / 2
    centro_y = (linha_bbox[1] + linha_bbox[3]) / 2
    return tabela_bbox[0] <= centro_x <= tabela_bbox[2] and tabela_bbox[1] <= centro_y <= tabela_bbox[3]


def _normalizar_celula_tabela(valor: object) -> str:
    if valor is None:
        return ""
    return _juntar_linhas_do_bloco(str(valor).splitlines())


def _serializar_tabela(tabela: object) -> str:
    linhas = tabela.extract()
    operacional = any(
        len(linha) == 3
        and any("O QUE FAZER" in normalized_for_match(celula or "") for celula in linha)
        for linha in linhas
    ) or any(
        len(linha) == 3
        and bool(linha[0])
        and (
            _ATIVIDADE_TABELA_RE.match(str(linha[0]))
            or normalized_for_match(str(linha[0])).startswith(("COMO FAZER", "PORQUE FAZER"))
        )
        for linha in linhas
    )

    serializadas: list[str] = []
    for linha in linhas:
        preservar_lista = (
            not operacional
            and len(linhas) == 1
            and any(_LIST_ITEM_RE.search(str(celula or "")) for celula in linha)
        )
        celulas = [
            _normalizar_celula_tabela(celula)
            if preservar_lista or operacional
            else " ".join(str(celula or "").split())
            for celula in linha
        ]
        if not any(celulas):
            continue
        if operacional and len(celulas) == 3:
            primeira = celulas[0]
            normalizada = normalized_for_match(primeira)
            if "O QUE FAZER" in normalizada:
                serializadas.append("O QUE FAZER EXECUTANTE ONDE REGISTRAR")
                continue
            if _ATIVIDADE_TABELA_RE.match(primeira) and (celulas[1] or celulas[2]):
                serializadas.append(primeira)
                continue
            if normalizada.startswith("COMO FAZER"):
                partes = re.split(r"(?=PORQUE\s+FAZER\s*:)", primeira, maxsplit=1, flags=re.IGNORECASE)
                serializadas.extend(parte.strip() for parte in partes if parte.strip())
                continue
        serializadas.append("• " + " | ".join(celula for celula in celulas if celula))
    return ("\n\n" if operacional else "\n").join(serializadas)


def _extrair_pagina_com_tabelas(page: fitz.Page, tabelas: list[object]) -> str:
    eventos: list[tuple[float, str]] = []
    bboxes_tabelas = [tabela.bbox for tabela in tabelas]
    pagina_dict = page.get_text("dict", sort=True)
    for bloco in pagina_dict.get("blocks", []):
        if bloco.get("type") != 0:
            continue
        linhas_fora: list[str] = []
        posicao_y: float | None = None
        for linha in bloco.get("lines", []):
            bbox = tuple(linha.get("bbox", (0, 0, 0, 0)))
            dentro = any(_linha_dentro_de_tabela(bbox, tabela_bbox) for tabela_bbox in bboxes_tabelas)
            texto_linha = "".join(span.get("text", "") for span in linha.get("spans", [])).strip()
            if dentro or not texto_linha:
                if linhas_fora:
                    eventos.append((posicao_y or 0, "\n".join(linhas_fora)))
                    linhas_fora = []
                    posicao_y = None
                continue
            if posicao_y is None:
                posicao_y = bbox[1]
            linhas_fora.append(texto_linha)
        if linhas_fora:
            eventos.append((posicao_y or 0, "\n".join(linhas_fora)))

    eventos.extend((tabela.bbox[1], _serializar_tabela(tabela)) for tabela in tabelas)
    return "\n\n".join(texto for _, texto in sorted(eventos, key=lambda evento: evento[0]) if texto.strip())


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrai texto preservando parágrafos nas páginas predominantemente textuais."""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            paginas: list[str] = []
            for page in document:
                tabelas_relevantes = [
                    tabela
                    for tabela in page.find_tables().tables
                    if tabela.bbox[3] - tabela.bbox[1] >= 40
                ]
                if tabelas_relevantes:
                    paginas.append(_extrair_pagina_com_tabelas(page, tabelas_relevantes))
                    continue

                blocos_textuais = [
                    bloco[4].strip()
                    for bloco in page.get_text("blocks", sort=True)
                    if bloco[6] == 0 and bloco[4].strip()
                ]
                paginas.append("\n\n".join(blocos_textuais))
            return "\n\n".join(paginas)
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise ValueError("Não foi possível extrair texto do PDF.") from exc


def limpar_texto_pdf(texto: str) -> str:
    linhas_limpas: list[str] = []
    for linha in texto.splitlines():
        linha = normalize_whitespace(linha)
        linha = re.sub(r"(?<=\d)\.\.(?=\d)", ".", linha)
        linha = _PAGE_RE.sub("", linha).strip()
        normalizada = normalized_for_match(linha)
        if not linha:
            if linhas_limpas and linhas_limpas[-1] != "":
                linhas_limpas.append("")
            continue
        if linha in {"_", "."} or normalizada == "INTERNA" or _UNDERSCORE_RE.match(linha):
            continue
        if _NOISE_LINE_RE.match(linha):
            continue
        if normalizada.startswith(("APROVADO POR", "GERIDO POR", "GESTÃO DO DOCUMENTO", "GESTAO DO DOCUMENTO")):
            continue
        linhas_limpas.append(linha)
    return "\n".join(linhas_limpas).strip()


def detectar_categoria(texto: str) -> str:
    normalizado = normalized_for_match(texto)
    primeira_linha = texto.splitlines()[0] if texto else ""
    texto_sem_item = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*(?:[-–—]\s*)?", "", normalizado)
    if _DOCUMENT_CODE_RE.match(primeira_linha):
        return "padrao_documento"
    if _ANEXO_DOCUMENTO_RE.match(primeira_linha.strip()):
        return "anexo_documento"
    if (
        _TABLE_HEADER_RE.match(primeira_linha)
        or all(termo in normalizado for termo in ("O QUE FAZER", "EXECUTANTE", "ONDE REGISTRAR"))
        or all(termo in normalizado for termo in ("ATIVIDADE", "ASPECTO/PERIGO", "ACOES DE CONTROLE"))
        or normalizado == "QUEM O QUE"
    ):
        return "cabecalho_tabela"
    if _TABLE_RE.match(texto):
        return "titulo_tabela"
    if _SECTION_RE.match(primeira_linha) and re.fullmatch(
        r"\d+\.\s+(?:OBJETIVO|APLICAÇÃO|DESCRIÇÃO|REGISTROS|DEFINIÇÕES)",
        primeira_linha.strip(),
        re.IGNORECASE,
    ):
        return "secao_principal"
    categorias = (
        ("objetivo", "objetivo"),
        ("aplicacao", "aplicação"),
        ("como_fazer", "como fazer"),
        ("porque_fazer", "porque fazer"),
        ("registros", "registro"),
        ("definicoes", "definiç"),
        ("recursos_necessarios", "recursos necessários"),
        ("itens_criticos", "itens críticos"),
    )
    for categoria, termo in categorias:
        if texto_sem_item.startswith(normalized_for_match(termo)):
            return categoria
    if re.search(r"^\s*\d+(?:\.\d+)+", texto):
        return "subsecao_numerada"
    if normalizado.startswith("ATIVIDADE"):
        return "atividade_tabela"
    if _SECTION_RE.match(texto):
        return "secao_principal"
    return "geral"


def detectar_escopo(texto: str) -> str:
    primeira_linha = texto.splitlines()[0] if texto else ""
    normalizado = normalized_for_match(primeira_linha)
    if normalizado.startswith("ANEXO A"):
        return "anexo_a"
    if normalizado.startswith("ANEXO B"):
        return "anexo_b"
    if normalizado.startswith("ANEXO"):
        return "anexo"
    tabela = re.match(r"^TABELA\s*(\d+)\b", normalizado)
    if tabela and tabela.group(1) in {"2", "5"}:
        return f"tabela_{tabela.group(1)}"
    if normalizado.startswith(("TABELA", "QUADRO")):
        return "tabelas_tecnicas"
    return "documento_principal" if _SECTION_RE.match(texto) else "geral"


def _inicia_secao_documento_fora_da_tabela(texto: str) -> bool:
    """Distingue uma seção do documento de uma atividade numerada dentro de uma tabela."""
    primeira_linha = texto.splitlines()[0] if texto else ""
    if re.match(r"^\d+(?:\.\d+)+\.?\s*[-–—]", primeira_linha):
        return True
    return re.fullmatch(
        r"\d+\.\s+(?:OBJETIVO|APLICAÇÃO|DESCRIÇÃO|REGISTROS|DEFINIÇÕES)",
        primeira_linha.strip(),
        re.IGNORECASE,
    ) is not None


def extrair_palavras_chave(texto: str) -> list[str]:
    normalizado = normalized_for_match(texto)
    termos = (
        "objetivo", "aplicação", "descrição", "tabela", "como fazer", "porque fazer",
        "anexo", "registro", "execução", "atividade", "recursos", "itens críticos",
        "ações de controle", "p.p.n.t", "boletim",
    )
    return [termo for termo in termos if normalized_for_match(termo) in normalizado]


def extrair_item_padrao(texto: str) -> str:
    primeira_linha = texto.splitlines()[0] if texto else ""
    resultado = _ITEM_PADRAO_RE.match(primeira_linha)
    return resultado.group(1) if resultado else ""


def _eh_titulo_de_sumario(bloco: list[str]) -> bool:
    if len(bloco) != 1:
        return False
    titulo = normalize_whitespace(bloco[0])
    return bool(re.fullmatch(r"\d+\.\s+.+", titulo)) and titulo.split(maxsplit=1)[1] in _SUMARIO_TITULOS


def _remover_sumario_inicial(blocos: list[list[str]]) -> list[list[str]]:
    """Remove a lista de capítulos inicial quando as mesmas seções aparecem depois com conteúdo."""
    indice_inicial = next(
        (indice for indice, bloco in enumerate(blocos) if _eh_titulo_de_sumario(bloco)),
        len(blocos),
    )
    sumario: list[list[str]] = []
    titulos_vistos: set[str] = set()
    for bloco in blocos[indice_inicial:]:
        if not _eh_titulo_de_sumario(bloco):
            break
        titulo = normalize_whitespace(bloco[0])
        if titulo in titulos_vistos:
            break
        sumario.append(bloco)
        titulos_vistos.add(titulo)
    if len(sumario) < 3:
        return blocos

    titulos_repetidos = {normalize_whitespace(bloco[0]) for bloco in sumario}
    inicio_conteudo = indice_inicial + len(sumario)
    if any(
        normalize_whitespace(bloco[0]) in titulos_repetidos
        for bloco in blocos[inicio_conteudo:]
        if bloco
    ):
        return [*blocos[:indice_inicial], *blocos[inicio_conteudo:]]
    return blocos


def _agrupar_cabecalho_documento(blocos: list[list[str]]) -> list[list[str]]:
    if len(blocos) < 2 or not _DOCUMENT_CODE_RE.match(normalize_whitespace(blocos[0][0])):
        return blocos
    titulo = " ".join(normalize_whitespace(linha) for linha in blocos[1])
    if not titulo or _SECTION_RE.match(titulo) or titulo != titulo.upper():
        return blocos
    return [[*blocos[0], *blocos[1]], *blocos[2:]]


def _eh_titulo_estrutural(linha: str) -> bool:
    linha = normalize_whitespace(linha)
    if re.fullmatch(
        r"\d+\.\s+(?:OBJETIVO|APLICAÇÃO|DESCRIÇÃO|REGISTROS|DEFINIÇÕES)",
        linha,
        re.IGNORECASE,
    ):
        return True
    # Um número isolado seguido de hífen costuma ser item de lista, não seção.
    return re.match(r"^\d+\.\d+(?:\.\d+)*\.?\s*[-–—]\s*\S+", linha) is not None


def _item_numerado_da_linha(linha: str) -> str:
    correspondencia = _NUMBERED_ITEM_RE.match(normalize_whitespace(linha))
    if not correspondencia:
        return ""
    return correspondencia.group(1).rstrip(".")


def _linha_numerada_e_instrucao(linha: str, tem_subitens: bool, resumo_anexo: bool) -> bool:
    """Distingue um passo operacional de um título hierárquico em anexos e manuais."""
    correspondencia = _NUMBERED_ITEM_RE.match(normalize_whitespace(linha))
    if not correspondencia or tem_subitens or _ANEXO_OPERATIONAL_HEADING_RE.match(linha):
        return False
    item = correspondencia.group(1).rstrip(".")
    conteudo = correspondencia.group(2).lstrip("-–— ").strip()
    niveis = len(item.split(".")) if item else 0
    if not conteudo or conteudo == conteudo.upper():
        return False
    if resumo_anexo:
        return False
    return niveis == 1 or _ACTION_IMPERATIVE_RE.search(conteudo) is not None


def _formatar_item_do_anexo(item: str, escopo: str) -> str:
    if not item or not escopo.startswith("anexo_"):
        return item
    letra = escopo.removeprefix("anexo_").upper()
    return f"Anexo {letra} - {item}"


def _parece_fragmento_interface(texto: str) -> bool:
    normalizado = normalized_for_match(texto)
    if not normalizado:
        return True
    if re.fullmatch(r"\d+(?:\s+\d+){0,3}", normalizado):
        return True
    if normalizado in {
        "ALT", "CONFIG", "FLOW COMP", "LIST", "METER", "OBS", "USER",
        "VALOR TOTALIZADO DO GAS",
    }:
        return True
    if texto.lstrip().startswith(".:"):
        return True
    palavras = normalizado.split()
    letras_isoladas = sum(len(palavra) == 1 for palavra in palavras)
    return len(palavras) >= 4 and letras_isoladas / len(palavras) >= 0.5


def _marcar_sufixo_de_interface(blocos: list[dict]) -> None:
    """Descarta OCR de telas anexadas quando ele forma um sufixo técnico isolado."""
    inicio = next(
        (
            indice
            for indice in range(len(blocos) - 1, -1, -1)
            if blocos[indice].get("categoria") == "cabecalho_documento_repetido"
        ),
        len(blocos),
    )
    sufixo = blocos[inicio:]
    if len(sufixo) < 5:
        return
    fragmentos = sum(_parece_fragmento_interface(str(bloco.get("texto") or "")) for bloco in sufixo)
    if fragmentos / len(sufixo) < 0.5:
        return
    tem_estrutura_documental = any(
        bloco.get("itemPadraoDetectado")
        or bloco.get("categoria") in {"instrucao_operacional", "secao_principal", "subsecao_numerada"}
        for bloco in sufixo
    )
    for bloco in sufixo:
        if not tem_estrutura_documental or (
            bloco.get("categoria") == "cabecalho_documento_repetido"
            or _parece_fragmento_interface(str(bloco.get("texto") or ""))
        ):
            bloco["categoria"] = "fragmento_interface"
            bloco["tituloEstrutural"] = False


def _conteudo_item_numerado(texto: str) -> str:
    correspondencia = _NUMBERED_ITEM_RE.match(normalize_whitespace(texto))
    return correspondencia.group(2).lstrip("-–— ").strip() if correspondencia else ""


def _conteudo_em_caixa_alta(texto: str) -> bool:
    conteudo = _conteudo_item_numerado(texto)
    letras = [caractere for caractere in conteudo if caractere.isalpha()]
    maiusculas = sum(caractere.isupper() for caractere in letras)
    return bool(letras) and maiusculas / len(letras) >= 0.9


def _formatar_item_local_do_anexo(item_pai: str, item_local: str, escopo: str) -> str:
    pai = item_pai.rstrip(".")
    local = item_local.strip().strip("()").rstrip(".")
    separador = "" if pai[-1:].isalpha() else "."
    return _formatar_item_do_anexo(f"{pai}{separador}({local}.)", escopo)


def _aplicar_hierarquia_local_do_anexo(blocos: list[dict]) -> None:
    """Reconstrói a numeração local das listas automáticas do Word em cada procedimento."""
    item_pai = ""
    em_procedimento = False
    contador_local = 0

    for bloco in blocos:
        if not str(bloco.get("escopo") or "").startswith("anexo_"):
            item_pai = ""
            em_procedimento = False
            contador_local = 0
            continue

        texto = str(bloco.get("texto") or "").strip()
        item_fonte = str(bloco.get("itemPadraoFonte") or "").strip()
        titulo_alfanumerico = _ANEXO_ALPHANUMERIC_HEADING_RE.match(texto)
        if titulo_alfanumerico:
            item_pai = titulo_alfanumerico.group(1).upper()
            em_procedimento = True
            contador_local = 0
            bloco["itemPadraoFonte"] = item_pai
            bloco["itemPadraoDetectado"] = _formatar_item_do_anexo(item_pai, str(bloco.get("escopo")))
            bloco["categoria"] = "subsecao_numerada"
            bloco["tituloEstrutural"] = True
            bloco["secaoContextual"] = bloco["itemPadraoDetectado"]
            continue
        if item_fonte and _conteudo_em_caixa_alta(texto):
            item_pai = item_fonte.rstrip(".")
            em_procedimento = False
            contador_local = 0
            if bloco.get("categoria") == "item_numerado_anexo":
                bloco["categoria"] = "subsecao_numerada"
            bloco["tituloEstrutural"] = True
            bloco["secaoContextual"] = _formatar_item_do_anexo(item_fonte, str(bloco.get("escopo")))
            continue

        if normalized_for_match(texto).rstrip(".") == "PROCEDIMENTO" and item_pai:
            em_procedimento = True
            contador_local = 0
            bloco["categoria"] = "secao_principal"
            bloco["tituloEstrutural"] = True
            bloco["secaoContextual"] = _formatar_item_do_anexo(item_pai, str(bloco.get("escopo")))
            continue

        if not em_procedimento or not item_pai or texto.upper().startswith("OBS"):
            continue

        if item_fonte:
            primeiro_nivel = item_fonte.rstrip(".").split(".", maxsplit=1)[0]
            if primeiro_nivel.isdigit():
                contador_local = max(contador_local, int(primeiro_nivel))
            bloco["itemPadraoDetectado"] = _formatar_item_local_do_anexo(
                item_pai,
                item_fonte,
                str(bloco.get("escopo")),
            )
        elif _ACTION_IMPERATIVE_RE.search(texto):
            contador_local += 1
            bloco["itemPadraoDetectado"] = _formatar_item_local_do_anexo(
                item_pai,
                str(contador_local),
                str(bloco.get("escopo")),
            )
        else:
            continue

        bloco["secaoContextual"] = _formatar_item_do_anexo(item_pai, str(bloco.get("escopo"))).rstrip(".")
        item_local_com_filhos = bool(
            item_fonte
            and bloco.get("temSubitens")
            and len(item_fonte.rstrip(".").split(".")) == 1
        )
        bloco["tituloEstrutural"] = item_local_com_filhos
        texto_sem_item = _conteudo_item_numerado(texto) or texto
        if item_local_com_filhos:
            bloco["categoria"] = "secao_principal"
        elif normalized_for_match(texto_sem_item).startswith("SE NAO"):
            bloco["categoria"] = "geral"
        else:
            bloco["categoria"] = "instrucao_operacional"
            bloco["acaoUnica"] = True


def _bloco_e_lista_numerada(bloco: list[str]) -> bool:
    return bool(bloco) and all(_NUMBERED_LIST_ITEM_RE.match(normalize_whitespace(linha)) for linha in bloco)


def _bloco_e_lista_visual(bloco: list[str]) -> bool:
    if not bloco:
        return False
    primeira = normalize_whitespace(bloco[0])
    return (
        _LIST_ITEM_RE.match(primeira) is not None
        and _SECTION_RE.match(primeira) is None
        and not _eh_titulo_estrutural(primeira)
    )


def _deve_unir_continuacao(bloco: list[str], seguinte: list[str]) -> bool:
    if not bloco or not seguinte:
        return False
    anterior = normalize_whitespace(bloco[-1])
    proxima = normalize_whitespace(seguinte[0])
    if not anterior or not proxima or _SECTION_RE.match(proxima) or _TABLE_RE.match(proxima):
        return False
    if _eh_titulo_estrutural(bloco[0]) and not anterior.lower().endswith((" e", " ou")):
        return False
    inicia_continuacao = proxima[0].islower() or proxima.upper().startswith(("PSIG ", "KGF/", "CM2 "))
    termina_aberto = anterior.endswith((",", ";", ":", " e", " ou")) or anterior[-1] not in ".!?"
    return inicia_continuacao and termina_aberto


def _agrupar_fragmentos_logicos(blocos: list[list[str]]) -> list[list[str]]:
    """Reconstrói listas, tabelas e frases quebradas sem depender do documento de exemplo."""
    agrupados: list[list[str]] = []
    indice = 0
    while indice < len(blocos):
        atual = list(blocos[indice])

        if _bloco_e_lista_numerada(atual):
            indice += 1
            while indice < len(blocos) and _bloco_e_lista_numerada(blocos[indice]):
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        if _bloco_e_lista_visual(atual):
            marcador = normalize_whitespace(atual[0])[:1]
            indice += 1
            while (
                indice < len(blocos)
                and _bloco_e_lista_visual(blocos[indice])
                and normalize_whitespace(blocos[indice][0])[:1] == marcador
                and sum(len(linha) + 1 for linha in [*atual, *blocos[indice]]) <= _MAX_GROUPED_TABLE_CHARACTERS
            ):
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        primeira = normalize_whitespace(atual[0]) if atual else ""
        if _TECHNICAL_GROUP_HEADER_RE.match(primeira):
            indice += 1
            while indice < len(blocos):
                proxima = normalize_whitespace(blocos[indice][0]) if blocos[indice] else ""
                if _TECHNICAL_GROUP_HEADER_RE.match(proxima):
                    break
                if not _TECHNICAL_PARAMETER_RE.match(proxima) and not _deve_unir_continuacao(atual, blocos[indice]):
                    break
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        indice += 1
        while indice < len(blocos) and _deve_unir_continuacao(atual, blocos[indice]):
            atual.extend(blocos[indice])
            indice += 1
        agrupados.append(atual)
    return agrupados


def _texto_tem_acoes_explicitas(texto: str) -> bool:
    sem_negativas = _NEGATIVE_ACTION_RE.sub("", texto)
    if _ACTION_START_RE.match(sem_negativas):
        return True
    normalizado = normalized_for_match(sem_negativas)
    if "DEVE-SE SEGUIR" in normalizado or "RECOMENDA-SE COLETAR" in normalizado:
        return True
    return len(_ACTION_CUE_RE.findall(sem_negativas)) >= 2


def _item_numerado_tem_acao_explicita(texto: str) -> bool:
    sem_negativas = _NEGATIVE_ACTION_RE.sub("", texto)
    return _ACTION_CUE_RE.search(sem_negativas) is not None


def _juntar_linhas_do_bloco(linhas: list[str]) -> str:
    """Remove quebras visuais do PDF e mantém itens de uma lista na mesma célula."""
    linhas_logicas: list[str] = []
    for linha in linhas:
        trecho = normalize_whitespace(linha)
        if not trecho:
            continue
        if _LIST_ITEM_RE.match(trecho) and linhas_logicas:
            linhas_logicas.append(trecho)
        elif linhas_logicas:
            linhas_logicas[-1] = f"{linhas_logicas[-1]} {trecho}".strip()
        else:
            linhas_logicas.append(trecho)
    return "\n".join(linhas_logicas)


def separar_blocos(texto: str) -> list[dict]:
    """Separa segmentos técnicos pequenos, ordenados e adequados à conversão pela IA."""
    blocos: list[list[str]] = []
    atual: list[str] = []
    escopo_tabela_linear: str | None = None
    for linha in texto.splitlines():
        if not linha.strip():
            if atual:
                blocos.append(atual)
                atual = []
            continue

        escopo_da_linha = detectar_escopo(linha)
        if escopo_da_linha in {"tabela_2", "tabela_5"}:
            escopo_tabela_linear = escopo_da_linha
        elif escopo_tabela_linear and _inicia_secao_documento_fora_da_tabela(linha):
            escopo_tabela_linear = None

        titulo_estrutural = _eh_titulo_estrutural(linha)
        titulo_tabela = _TABLE_RE.match(linha) is not None
        item_de_tabela = (
            escopo_tabela_linear == "tabela_2"
            and _ATIVIDADE_TABELA_RE.match(linha) is not None
        )
        marcador_procedimento = normalized_for_match(linha).rstrip(".") == "PROCEDIMENTO"
        inicio_de_bloco = bool(
            _SECTION_RE.match(linha)
            or titulo_tabela
            or item_de_tabela
            or marcador_procedimento
            or _PROCESS_REFERENCE_RE.match(linha)
            or _TECHNICAL_MARKER_RE.match(linha)
        )
        if inicio_de_bloco and atual:
            blocos.append(atual)
            atual = []
        atual.append(linha)
        if titulo_estrutural or titulo_tabela or marcador_procedimento:
            blocos.append(atual)
            atual = []
            continue
        if sum(len(trecho) + 1 for trecho in atual) >= _MAX_BLOCK_CHARACTERS:
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    blocos = _agrupar_fragmentos_logicos(blocos)
    blocos = _agrupar_cabecalho_documento(blocos)
    blocos = _remover_sumario_inicial(blocos)
    segmentos_de_anexo: list[int] = []
    segmento_atual = 0
    for bloco in blocos:
        primeira_linha = normalize_whitespace(bloco[0]) if bloco else ""
        if _ANEXO_DOCUMENTO_RE.match(primeira_linha):
            segmento_atual += 1
        segmentos_de_anexo.append(segmento_atual)
    itens_numerados = [
        (segmentos_de_anexo[indice], _item_numerado_da_linha(bloco[0]))
        for indice, bloco in enumerate(blocos)
        if bloco and _item_numerado_da_linha(bloco[0])
    ]
    itens_com_subitens = {
        (segmento, item)
        for segmento, item in itens_numerados
        if any(
            outro_segmento == segmento and outro.startswith(f"{item}.")
            for outro_segmento, outro in itens_numerados
            if outro != item
        )
    }

    resultado: list[dict] = []
    escopo_contextual = "documento_principal"
    secao_contextual = ""
    atividade_contextual: dict[str, str] | None = None
    secao_principal_contextual = ""
    anexos_documento_vistos: set[str] = set()
    escopos_explicitos = {"anexo", "anexo_a", "anexo_b", "tabela_2", "tabela_5", "tabelas_tecnicas"}
    for ordem, linhas in enumerate(blocos, start=1):
        bloco_texto = _juntar_linhas_do_bloco(linhas)
        if not bloco_texto:
            continue
        escopo_detectado = detectar_escopo(bloco_texto)
        if escopo_detectado in escopos_explicitos:
            escopo_contextual = escopo_detectado
        elif (
            escopo_detectado == "documento_principal"
            and not escopo_contextual.startswith(("anexo", "tabela_"))
        ):
            escopo_contextual = escopo_detectado
        elif (
            escopo_detectado == "documento_principal"
            and escopo_contextual.startswith("tabela_")
            and _inicia_secao_documento_fora_da_tabela(bloco_texto)
        ):
            escopo_contextual = escopo_detectado
        if escopo_contextual != "tabela_2":
            atividade_contextual = None
        categoria = detectar_categoria(bloco_texto)
        if categoria == "anexo_documento":
            identificador_anexo = normalize_whitespace(linhas[0]).upper()
            if identificador_anexo in anexos_documento_vistos:
                categoria = "anexo_cabecalho_repetido"
            else:
                anexos_documento_vistos.add(identificador_anexo)
        elif categoria == "padrao_documento" and escopo_contextual.startswith("anexo_"):
            categoria = "cabecalho_documento_repetido"
        item_numerado_fonte = _item_numerado_da_linha(linhas[0])
        tem_subitens = (segmentos_de_anexo[ordem - 1], item_numerado_fonte) in itens_com_subitens
        resumo_anexo = max(segmentos_de_anexo, default=1) > 1 and segmentos_de_anexo[ordem - 1] == 1
        instrucao_numerada = _linha_numerada_e_instrucao(linhas[0], tem_subitens, resumo_anexo)
        if categoria == "secao_principal":
            secao_principal_contextual = normalized_for_match(bloco_texto)
        elif categoria == "geral" and secao_principal_contextual.endswith("OBJETIVO"):
            categoria = "objetivo"
        elif categoria == "geral" and secao_principal_contextual.endswith("APLICACAO"):
            categoria = "aplicacao"
        elif categoria == "geral" and secao_principal_contextual.endswith("DEFINICOES"):
            categoria = "definicoes"
        if escopo_contextual == "tabelas_tecnicas" and categoria not in {"titulo_tabela", "cabecalho_tabela"}:
            categoria = "tabela_tecnica"
        if escopo_contextual == "tabela_2" and categoria == "secao_principal":
            categoria = "atividade_tabela_2"
        if escopo_contextual == "tabela_5" and categoria == "secao_principal":
            categoria = "item_numerado_tabela_5"
        if categoria == "geral" and _LIST_ITEM_RE.match(linhas[0]):
            if escopo_contextual == "tabela_2":
                categoria = "atividade_tabela_2"
            elif escopo_contextual == "tabela_5":
                categoria = "atividade_anomalia"
        if instrucao_numerada and escopo_contextual not in {"tabela_2", "tabela_5"}:
            categoria = "instrucao_operacional"
        elif (
            escopo_contextual.startswith("anexo_")
            and categoria == "subsecao_numerada"
            and not tem_subitens
            and not _ANEXO_OPERATIONAL_HEADING_RE.match(linhas[0])
        ):
            categoria = "item_numerado_anexo"
        itens_de_lista = sum(_LIST_ITEM_RE.match(linha) is not None for linha in linhas)
        lista_agrupada = itens_de_lista >= 2 and escopo_contextual != "tabela_2"
        if lista_agrupada:
            if escopo_contextual not in {"tabelas_tecnicas", "tabela_5"}:
                categoria = "lista_informativa"
            elif categoria == "cabecalho_tabela" and escopo_contextual != "tabela_2":
                categoria = "tabela_tecnica"
        item_padrao_fonte = extrair_item_padrao(bloco_texto)
        item_padrao_detectado = _formatar_item_do_anexo(item_padrao_fonte, escopo_contextual)
        candidato_acao = _texto_tem_acoes_explicitas(bloco_texto) or (
            bool(item_padrao_detectado)
            and not _eh_titulo_estrutural(linhas[0])
            and _item_numerado_tem_acao_explicita(bloco_texto)
        )
        if bloco_texto and candidato_acao and categoria in {
            "geral",
            "subsecao_numerada",
            "registros",
        } and not _ANEXO_OPERATIONAL_HEADING_RE.match(linhas[0]):
            categoria = "instrucao_operacional"
        texto_sem_numeracao = re.sub(
            r"^\s*\d+(?:\.\d+)*\.?\s*",
            "",
            bloco_texto,
        )
        if texto_sem_numeracao.lower().startswith("não "):
            categoria = "geral"
        titulo_estrutural = (
            _eh_titulo_estrutural(linhas[0])
            and not instrucao_numerada
            and categoria != "item_numerado_anexo"
        )
        if bloco_texto and item_padrao_detectado and (titulo_estrutural or tem_subitens):
            secao_contextual = item_padrao_detectado.rstrip(".")
        contexto_tarefa: dict[str, str] = {}
        atividade_encontrada = _ATIVIDADE_TABELA_RE.match(linhas[0]) if escopo_contextual == "tabela_2" else None
        if categoria == "atividade_tabela_2" and atividade_encontrada:
            indice_atividade = atividade_encontrada.group(1)
            atividade_contextual = {
                "itemPadrao": f"{secao_contextual}.{indice_atividade}" if secao_contextual else "",
                "subtarefaHTA": f"{indice_atividade}.",
            }
            contexto_tarefa = atividade_contextual
        elif escopo_contextual == "tabela_2" and categoria in {"como_fazer", "porque_fazer"} and atividade_contextual:
            contexto_tarefa = atividade_contextual
        resultado.append(
            {
                "ordem": ordem,
                "texto": bloco_texto,
                "itemPadraoDetectado": item_padrao_detectado,
                "itemPadraoFonte": item_padrao_fonte,
                "categoria": categoria,
                "escopo": escopo_contextual,
                "palavras_chave": extrair_palavras_chave(bloco_texto),
                "contextoTarefa": contexto_tarefa,
                "secaoContextual": secao_contextual,
                "tituloEstrutural": titulo_estrutural,
                "listaAgrupada": lista_agrupada,
                "temSubitens": tem_subitens,
            }
        )
    _aplicar_hierarquia_local_do_anexo(resultado)
    _marcar_sufixo_de_interface(resultado)
    return resultado
