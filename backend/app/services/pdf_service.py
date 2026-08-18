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
_ANEXO_DOCUMENTO_RE = re.compile(r"^ANEXO\s+([A-Z]\d*)\b", re.IGNORECASE)
_ANEXO_FILENAME_RE = re.compile(
    r"^\s*ANEXO\s+([A-Z]\d*)\s*(?:[-–—:]\s*(.+?))?\s*(?:\.PDF|\.DOCX?|\.XLSM?)?$",
    re.IGNORECASE,
)
_TABLE_HEADER_RE = re.compile(
    r"^(?:O QUE FAZER|EXECUTANTE|ONDE REGISTRAR|ATIVIDADE|ASPECTO/PERIGO|IMPACTO/RISCO|AÇÕES DE CONTROLE)$",
    re.IGNORECASE,
)
_DOCUMENT_METADATA_RE = re.compile(
    r"^(?:"
    r"P\d{1,2}(?:\s*\|\s*P\d{1,2})+"
    r"|INSTALAÇÃO\b|ÁREA\b|DATA\b|RESP(?:ONSÁVEIS)?\b"
    r"|NOME\b|MATR[IÍ]CULA\b|FUNÇÃO\b|GERÊNCIA\b"
    r"|A[CÇ][AÃ]O\s+DE\s+RTA\b"
    r"|FIGURA\s+\d+\b|\d+\s+DE\s+\d+$"
    r"|(?:SIM|NÃO|NAO|RESP\.?|N\.?A\.?)$"
    r"|[A-Z]\.$"
    r")",
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
    r"|#?\s*INTERNA(?:\s*\\.*)?$"
    r")$",
    re.IGNORECASE,
)
_NUMBERED_ITEM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s*(?:[-–—]\s*)?(.*)$")
_ANEXO_ALPHANUMERIC_HEADING_RE = re.compile(
    r"^\s*(\d+[A-Z])\s*[-–—]\s*(.+)$",
    re.IGNORECASE,
)
_ACTION_IMPERATIVE_RE = re.compile(
    r"\b(?:aborte|abortar|acompanhe|acompanhar|acople|acoplar|abra|abrir|acione|acionar|"
    r"aguarde|aguardar|alinhe|alinhar|anote|anotar|aperte|apertar|baixe|baixar|clique|clicar|"
    r"comunique|comunicar|confirme|confirmar|digite|digitar|escolha|escolher|feche|fechar|informe|informar|"
    r"inspecione|inspecionar|instale|instalar|interrompa|interromper|isole|isolar|ligue|ligar|"
    r"observe|observar|posicione|posicionar|preencha|preencher|realize|realizar|recoloque|recolocar|"
    r"retorne|retornar|retire|retirar|solicite|solicitar|suba|subir|teste|testar|trave|travar|"
    r"utilize|utilizar|verifique|verificar|varie|variar)\b",
    re.IGNORECASE,
)
_OPERATIONAL_RESPONSIBLE_CELL_RE = re.compile(
    r"^(?:RESP\.?|OP[- ]?[A-Z0-9]+|CIOP(?:-[A-Z0-9]+)?|FSO(?:[- ]CIMA)?|BARCO\s+DE\s+APOIO)$",
    re.IGNORECASE,
)
_ANEXO_OPERATIONAL_HEADING_RE = re.compile(
    r"^\s*\d+(?:\.\d+)*\.?\s*(?:[-–—]\s*)?"
    r"(?:ACOMPANHAR|CHECAR|INSPECIONAR|VERIFICAÇÃO|VERIFICACAO)\b",
    re.IGNORECASE,
)
_ANEXO_LETTER_ITEM_RE = re.compile(
    r"^\s*(?:[•·▪◦*\-]\s*([A-Z])(?:\s*[.)]|\s+)|([A-Z])\s*[.)])\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_OPERATIONAL_TABLE_ROW_RE = re.compile(r"^\s*PASSO\s+(\d+)\s*\|\s*(.+)$", re.IGNORECASE | re.DOTALL)
_OPERATIONAL_STAGE_RE = re.compile(r"^\s*ETAPA\s+(\d+)\s*[-–—:]\s*(.+)$", re.IGNORECASE)
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
    r"^\s*(?:\d+(?:\.\d+)+\.?\s+)?(?:abortar|abrir|acionar|acoplar|aguardar|ajustar|"
    r"alinhar|anotar|aplicar|atentar|atuar|avaliar|bloquear|coletar|comunicar|confirmar|"
    r"contatar|desligar|emitir|encaminhar|entrar\s+em\s+contato|estabelecer|executar|"
    r"fechar|informar|iniciar|inspecionar|instalar|interromper|isolar|liberar|ligar|manter|"
    r"medir|monitorar|operar|parar|posicionar|preencher|proceder|realizar|registrar|remover|reparar|"
    r"restabelecer|retirar|seguir|sinalizar|solicitar|tomar|transportar|verificar)\b",
    re.IGNORECASE,
)
_ACTION_CUE_RE = re.compile(
    r"\b(?:dever[aá]|dever[aã]o|deve-se|recomenda-se|abortar|abrir|aguardar|isolar|ligar|"
    r"realizar|solicitar|bloquear|acionar|"
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
        any(
            marcador in normalized_for_match(celula or "")
            for celula in linha
            for marcador in ("O QUE FAZER", "PASSO")
        )
        and any("DESCRICAO" in normalized_for_match(celula or "") for celula in linha)
        for linha in linhas
    ) or any(
        len(linha) >= 2
        and str(linha[0] or "").strip().isdigit()
        and _ACTION_START_RE.match(str(linha[1] or "").strip()) is not None
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
    descricao_antecipada = ""
    for indice_linha, linha in enumerate(linhas):
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
        if operacional and len(celulas) >= 2:
            primeira = celulas[0]
            normalizada = normalized_for_match(primeira)
            if "O QUE FAZER" in normalizada:
                serializadas.append("O QUE FAZER EXECUTANTE ONDE REGISTRAR")
                continue
            if normalizada == "PASSO" and any("DESCRICAO" in normalized_for_match(celula) for celula in celulas):
                continue
            if not primeira and celulas[1] and indice_linha + 1 < len(linhas):
                proxima = [_normalizar_celula_tabela(celula) for celula in linhas[indice_linha + 1]]
                if proxima and proxima[0].isdigit() and (len(proxima) < 2 or not proxima[1]):
                    descricao_antecipada = celulas[1]
                    continue
            if primeira.isdigit() and (celulas[1] or descricao_antecipada):
                serializadas.append(f"PASSO {primeira} | {celulas[1] or descricao_antecipada}")
                descricao_antecipada = ""
                continue
            if not primeira and celulas[1] and serializadas and serializadas[-1].startswith("PASSO "):
                serializadas[-1] = f"{serializadas[-1]} {celulas[1]}".strip()
                continue
            if _ATIVIDADE_TABELA_RE.match(primeira) and any(celulas[1:]):
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
    marcador_lista_pendente = False
    for linha in texto.splitlines():
        linha = normalize_whitespace(linha)
        linha = linha.replace("\uf020", "").strip()
        # Alguns PDFs do Word usam o glifo privado U+F0B7 para marcadores. Ele
        # pode aparecer mais de uma vez na mesma linha extraída.
        linha = re.sub(r"\s*\uf0b7\s*", "\n• ", linha).strip()
        if linha == "\uf0fc":
            marcador_lista_pendente = True
            continue
        if linha.startswith("\uf0fc"):
            linha = f"• {linha.removeprefix(chr(0xF0FC)).strip()}"
            marcador_lista_pendente = False
        elif marcador_lista_pendente and linha:
            linha = f"• {linha}"
            marcador_lista_pendente = False
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
    if _DOCUMENT_METADATA_RE.match(normalizado):
        return "fragmento_interface"
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
    if re.match(r"^FIGURA\s*\d+\s*[-–—:]\s*DETALHAMENTO\s+DAS\s+ATIVIDADES", normalizado):
        return "titulo_tabela"
    if _TABLE_RE.match(texto) and "INDICADOR DE DESEMPENHO" in normalizado:
        return "geral"
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
    anexo = _ANEXO_DOCUMENTO_RE.match(primeira_linha.strip())
    if anexo:
        return f"anexo_{anexo.group(1).lower()}"
    if normalizado.startswith("ANEXO"):
        return "anexo"
    tabela = re.match(r"^TABELA\s*(\d+)\b", normalizado)
    if tabela and tabela.group(1) in {"2", "5"}:
        return f"tabela_{tabela.group(1)}"
    if normalizado.startswith(("TABELA", "QUADRO")):
        return "tabelas_tecnicas"
    return "documento_principal" if _SECTION_RE.match(texto) else "geral"


def _identificar_anexo_pelo_nome(nome_arquivo: str) -> tuple[str, str]:
    nome = str(nome_arquivo or "").strip()
    nome_sem_extensao = re.sub(r"\.(?:pdf|docx?|DOCX?)\s*$", "", nome).strip()
    correspondencia = re.search(
        r"\bANEXO\s+([A-Z]\d*)\b(?:\s*[-–—:]\s*(.*))?$",
        nome_sem_extensao,
        re.IGNORECASE,
    )
    if not correspondencia:
        return "", ""
    identificador = correspondencia.group(1).upper()
    titulo = str(correspondencia.group(2) or "").strip()
    return identificador, titulo


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
    if escopo.startswith("anexo_arquivo_"):
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
            # Nos anexos, os dois primeiros niveis numerados representam a
            # estrutura da atividade. A partir do terceiro nivel, textos em
            # caixa alta normalmente identificam equipamento/controlador e,
            # na matriz, sao classificados como Informacao, nao como titulo.
            profundidade_item = len(item_fonte.rstrip(".").split("."))
            eh_titulo_estrutural = profundidade_item <= 2
            item_pai = item_fonte.rstrip(".")
            em_procedimento = False
            contador_local = 0
            if eh_titulo_estrutural and bloco.get("categoria") == "item_numerado_anexo":
                bloco["categoria"] = "subsecao_numerada"
            elif not eh_titulo_estrutural:
                bloco["categoria"] = "item_numerado_anexo"
            bloco["tituloEstrutural"] = eh_titulo_estrutural
            bloco["secaoContextual"] = _formatar_item_do_anexo(item_fonte, str(bloco.get("escopo")))
            continue

        if normalized_for_match(texto).rstrip(".") == "PROCEDIMENTO" and item_pai:
            em_procedimento = True
            contador_local = 0
            bloco["categoria"] = "geral"
            bloco["tituloEstrutural"] = False
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
        texto_sem_item = _conteudo_item_numerado(texto) or texto
        item_local_com_filhos = bool(
            item_fonte
            and bloco.get("temSubitens")
            and len(item_fonte.rstrip(".").split(".")) == 1
            and re.search(r"\b(?:como\s+segue|seguintes\s+passos)\b", texto_sem_item, re.IGNORECASE)
        )
        bloco["tituloEstrutural"] = item_local_com_filhos
        if item_local_com_filhos:
            bloco["categoria"] = "secao_principal"
        elif normalized_for_match(texto_sem_item).startswith(("SE NAO", "NAO HAVENDO")):
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


def _bloco_e_lista_pontilhada(bloco: list[str]) -> bool:
    """Identifica checklists visuais cujo conteúdo deve permanecer em uma célula."""
    if not _bloco_e_lista_visual(bloco):
        return False
    return re.search(r"\.{3,}", normalize_whitespace(bloco[0])) is not None


def _deve_unir_continuacao(bloco: list[str], seguinte: list[str]) -> bool:
    if not bloco or not seguinte:
        return False
    anterior = normalize_whitespace(bloco[-1])
    proxima = normalize_whitespace(seguinte[0])
    if not anterior or not proxima or _SECTION_RE.match(proxima):
        return False
    proxima_e_tabela = _TABLE_RE.match(proxima) is not None
    if proxima_e_tabela:
        # Uma quebra visual pode cair exatamente antes de uma referência a
        # tabela/figura, sem que isso represente um novo título.
        if anterior.lower().endswith((" na", " no", " à", " ao", " pela", " pelo")):
            return True
        return False
    if (
        _eh_titulo_estrutural(bloco[0])
        and not _ACTION_IMPERATIVE_RE.search(anterior)
        and not anterior.lower().endswith((" e", " ou"))
    ):
        return False
    # Hifens de códigos/equipamentos e frases cortadas por paginação não são
    # delimitadores semânticos; a próxima linha completa a mesma ação.
    if anterior.endswith("-") or (anterior.endswith((",", ";")) and proxima[:1].islower()):
        return True
    # PDFs frequentemente quebram códigos/equipamentos de um mesmo item de lista
    # em um bloco novo. Enquanto a frase anterior estiver aberta, preserve a célula.
    if (
        _LIST_ITEM_RE.match(normalize_whitespace(bloco[0]))
        and not _SECTION_RE.match(normalize_whitespace(bloco[0]))
        and not _LIST_ITEM_RE.match(proxima)
        and anterior[-1] not in ".!?;"
    ):
        return True
    inicia_continuacao = proxima[0].islower() or proxima.upper().startswith(("PSIG ", "KGF/", "CM2 "))
    termina_aberto = anterior.endswith((",", ";", ":", " e", " ou")) or anterior[-1] not in ".!?"
    return inicia_continuacao and termina_aberto


def _agrupar_fragmentos_logicos(
    blocos: list[list[str]],
    agrupar_listas_visuais: bool = True,
) -> list[list[str]]:
    """Reconstrói listas, tabelas e frases quebradas sem depender do documento de exemplo."""
    agrupados: list[list[str]] = []
    indice = 0
    while indice < len(blocos):
        atual = list(blocos[indice])

        if _bloco_e_lista_pontilhada(atual):
            indice += 1
            while (
                indice < len(blocos)
                and _bloco_e_lista_pontilhada(blocos[indice])
                and sum(len(linha) + 1 for linha in [*atual, *blocos[indice]]) <= _MAX_GROUPED_TABLE_CHARACTERS
            ):
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        if _bloco_e_lista_numerada(atual):
            indice += 1
            while indice < len(blocos) and _bloco_e_lista_numerada(blocos[indice]):
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        if agrupar_listas_visuais and _bloco_e_lista_visual(atual):
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


def separar_blocos(texto: str, nome_arquivo: str = "") -> list[dict]:
    """Separa segmentos técnicos pequenos, ordenados e adequados à conversão pela IA."""
    identificador_anexo_arquivo, titulo_anexo_arquivo = _identificar_anexo_pelo_nome(nome_arquivo)
    anexo_standalone = bool(identificador_anexo_arquivo)
    fluxograma_standalone = anexo_standalone and bool(re.search(r"\bFLUXOGRAMA\b", nome_arquivo, re.IGNORECASE))
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
        item_de_lista_standalone = bool(anexo_standalone and _LIST_ITEM_RE.match(linha))
        titulo_raiz_standalone = bool(
            anexo_standalone and re.match(r"^\s*\d+\s*[-–—]\s*\S+", linha)
        )
        inicio_de_bloco = bool(
            _SECTION_RE.match(linha)
            or titulo_tabela
            or item_de_tabela
            or item_de_lista_standalone
            or titulo_raiz_standalone
            or _OPERATIONAL_TABLE_ROW_RE.match(linha)
            or _OPERATIONAL_STAGE_RE.match(linha)
            or marcador_procedimento
            or _PROCESS_REFERENCE_RE.match(linha)
            or _TECHNICAL_MARKER_RE.match(linha)
            or fluxograma_standalone
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
    blocos = _agrupar_fragmentos_logicos(
        blocos,
        agrupar_listas_visuais=not anexo_standalone,
    )
    blocos = _agrupar_cabecalho_documento(blocos)
    blocos = _remover_sumario_inicial(blocos)
    if anexo_standalone:
        if blocos:
            primeiro_texto = _juntar_linhas_do_bloco(blocos[0])
            letras = [caractere for caractere in primeiro_texto if caractere.isalpha()]
            primeiro_e_titulo = bool(letras) and sum(c.isupper() for c in letras) / len(letras) >= 0.85
            primeiro_e_titulo = primeiro_e_titulo and not bool(_SECTION_RE.match(primeiro_texto))
            if primeiro_e_titulo:
                titulo_anexo_arquivo = primeiro_texto
                blocos = blocos[1:]
            elif (
                titulo_anexo_arquivo
                and normalized_for_match(primeiro_texto) == normalized_for_match(titulo_anexo_arquivo)
            ):
                blocos = blocos[1:]
        cabecalho_anexo = [f"ANEXO {identificador_anexo_arquivo}"]
        if titulo_anexo_arquivo:
            cabecalho_anexo.append(titulo_anexo_arquivo)
        blocos.insert(0, cabecalho_anexo)
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
    escopo_contextual = (
        f"anexo_fluxograma_{identificador_anexo_arquivo.lower()}"
        if fluxograma_standalone
        else f"anexo_arquivo_{identificador_anexo_arquivo.lower()}"
        if anexo_standalone
        else "documento_principal"
    )
    secao_contextual = ""
    atividade_contextual: dict[str, str] | None = None
    secao_principal_contextual = ""
    secao_atividade_operacional = ""
    etapa_operacional = 0
    titulo_contextual = ""
    ultimo_item_operacional = ""
    anexos_documento_vistos: set[str] = set()
    escopos_explicitos = {"anexo", "tabela_2", "tabela_5", "tabelas_tecnicas"}
    for ordem, linhas in enumerate(blocos, start=1):
        bloco_texto = _juntar_linhas_do_bloco(linhas)
        if not bloco_texto:
            continue
        escopo_detectado = detectar_escopo(bloco_texto)
        if fluxograma_standalone:
            escopo_contextual = f"anexo_fluxograma_{identificador_anexo_arquivo.lower()}"
        elif anexo_standalone:
            escopo_contextual = f"anexo_arquivo_{identificador_anexo_arquivo.lower()}"
        elif escopo_detectado in escopos_explicitos or escopo_detectado.startswith("anexo_"):
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
        etapa_encontrada = _OPERATIONAL_STAGE_RE.match(bloco_texto)
        passo_operacional = _OPERATIONAL_TABLE_ROW_RE.match(bloco_texto)
        if etapa_encontrada:
            etapa_operacional = int(etapa_encontrada.group(1))
            secao_atividade_operacional = secao_contextual
            categoria = "etapa_operacional"
        elif passo_operacional:
            categoria = "passo_tabela_operacional"
        elif (
            etapa_operacional
            and linhas
            and all(
                _OPERATIONAL_RESPONSIBLE_CELL_RE.fullmatch(normalize_whitespace(linha))
                for linha in linhas
            )
        ):
            categoria = "fragmento_interface"
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
            if categoria == "passo_tabela_operacional":
                pass
            elif escopo_contextual not in {"tabelas_tecnicas", "tabela_5"}:
                categoria = "lista_informativa"
            elif categoria == "cabecalho_tabela" and escopo_contextual != "tabela_2":
                categoria = "tabela_tecnica"
        item_padrao_fonte = extrair_item_padrao(bloco_texto)
        if anexo_standalone and not item_padrao_fonte and re.match(r"^\s*\d+\s*[-–—]\s*\S+", bloco_texto):
            item_padrao_fonte = f"{item_numerado_fonte}-"
        item_padrao_detectado = _formatar_item_do_anexo(item_padrao_fonte, escopo_contextual)
        item_letra_anexo = _ANEXO_LETTER_ITEM_RE.match(bloco_texto) if anexo_standalone else None
        if passo_operacional:
            numero_passo = passo_operacional.group(1)
            base_item = secao_atividade_operacional or secao_contextual
            item_padrao_detectado = f"{base_item.rstrip('.')}.{numero_passo}." if base_item else numero_passo
            item_padrao_fonte = ""
        elif item_letra_anexo:
            item_padrao_fonte = ""
            if re.search(r"\.{3,}", bloco_texto) or "RECURSOS NECESSARIOS" in titulo_contextual:
                item_padrao_detectado = ""
                categoria = "geral"
            else:
                letra_item = (item_letra_anexo.group(1) or item_letra_anexo.group(2)).lower()
                item_padrao_detectado = (
                    f"{secao_contextual.rstrip('.')}.({letra_item})"
                    if secao_contextual
                    else f"({letra_item})"
                )
                categoria = "instrucao_operacional"
                ultimo_item_operacional = item_padrao_detectado
        candidato_acao = _texto_tem_acoes_explicitas(bloco_texto) or (
            bool(item_padrao_detectado)
            and not _eh_titulo_estrutural(linhas[0])
            and _item_numerado_tem_acao_explicita(bloco_texto)
        )
        if bloco_texto and candidato_acao and categoria in {
            "geral",
            "subsecao_numerada",
            "registros",
            "itens_criticos",
            "item_numerado_anexo",
        } and not _ANEXO_OPERATIONAL_HEADING_RE.match(linhas[0]):
            categoria = "instrucao_operacional"
        conteudo_numerado = _conteudo_item_numerado(bloco_texto)
        conteudo_operacional = conteudo_numerado or re.sub(
            r"^\s*[•·▪◦*\-]\s*",
            "",
            bloco_texto,
        ).strip()
        remissao_etapa = (
            normalized_for_match(conteudo_operacional)
            .lstrip("-–— ")
            .startswith("SEGUIR ETAPA")
        )
        inicio_condicional = re.match(
            r"^(?:Antes de|Após|Em caso|Caso|Se houver|Quando)\b",
            conteudo_operacional,
            re.IGNORECASE,
        ) is not None
        if anexo_standalone and remissao_etapa:
            categoria = "geral"
            candidato_acao = False
        elif anexo_standalone and categoria == "item_numerado_anexo":
            if candidato_acao:
                categoria = "instrucao_operacional"
            else:
                categoria = "subsecao_numerada"
        if anexo_standalone and item_padrao_fonte.rstrip(".") in {"1", "2", "1-", "2-"}:
            categoria = "subsecao_numerada"
        if (
            anexo_standalone
            and secao_contextual.rstrip(".") == "1.1"
            and item_padrao_fonte
            and len(item_padrao_fonte.rstrip(".").split(".")) > 2
            and not candidato_acao
        ):
            categoria = "geral"
        if (
            anexo_standalone
            and len(secao_contextual.rstrip(".").split(".")) >= 3
            and secao_contextual.rstrip(".").endswith(".1")
            and re.match(r"^Antes de iniciar\b", bloco_texto, re.IGNORECASE)
        ):
            categoria = "instrucao_operacional"
            candidato_acao = True
        if (
            anexo_standalone
            and inicio_condicional
            and _ACTION_IMPERATIVE_RE.search(bloco_texto)
        ):
            candidato_acao = True
            categoria = "instrucao_operacional"
        if (
            fluxograma_standalone
            and categoria in {"geral", "lista_informativa", "subsecao_numerada"}
            and not candidato_acao
            and not normalized_for_match(bloco_texto).startswith(("OBS", "ORIENTAR", "INFORMAR"))
        ):
            categoria = "fragmento_interface"
        if (
            anexo_standalone
            and not item_padrao_fonte
            and "ITENS CRITICOS" in titulo_contextual
            and inicio_condicional
            and (
                len(secao_contextual.rstrip(".").split(".")) <= 2
                or normalized_for_match(conteudo_operacional).startswith("EM CASO DE MANUTENCAO")
            )
        ):
            item_padrao_detectado = ""
            categoria = "geral"
            candidato_acao = False
        if (
            anexo_standalone
            and ultimo_item_operacional
            and not item_padrao_detectado
            and inicio_condicional
            and _ACTION_IMPERATIVE_RE.search(bloco_texto)
            and "ITENS CRITICOS" not in titulo_contextual
        ):
            item_padrao_detectado = ultimo_item_operacional
            categoria = "instrucao_operacional"
            candidato_acao = True
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
            and not remissao_etapa
        )
        contexto_lista_informativa = any(
            marcador in titulo_contextual
            for marcador in ("RECURSOS NECESSARIOS", "ITENS CRITICOS", "PREMISSAS")
        )
        item_contextual = item_padrao_detectado.rstrip(".")
        eh_descendente_lista = bool(
            contexto_lista_informativa
            and secao_contextual
            and item_contextual.startswith(f"{secao_contextual.rstrip('.')}.")
        )
        if eh_descendente_lista and categoria == "subsecao_numerada":
            categoria = "geral"
        if categoria == "subsecao_numerada" and len(bloco_texto) <= 120:
            titulo_estrutural = not eh_descendente_lista
        if categoria in {"recursos_necessarios", "itens_criticos"}:
            titulo_estrutural = True
        if anexo_standalone and categoria == "subsecao_numerada" and len(bloco_texto) <= 180:
            titulo_estrutural = True
        if categoria == "etapa_operacional":
            titulo_estrutural = True
        if bloco_texto and item_padrao_detectado and (titulo_estrutural or tem_subitens):
            secao_contextual = item_padrao_detectado.rstrip(".")
            titulo_contextual = normalized_for_match(bloco_texto)
            if anexo_standalone and len(secao_contextual.split(".")) == 1:
                ultimo_item_operacional = ""
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
        if categoria == "passo_tabela_operacional":
            contexto_tarefa = {
                "itemPadrao": item_padrao_detectado,
                "grupoOperacional": (
                    secao_atividade_operacional
                    if etapa_operacional <= 1
                    else f"__etapa_{etapa_operacional}_{secao_atividade_operacional}"
                ),
            }
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
                "acaoUnica": bool(item_letra_anexo),
                "anexoStandalone": anexo_standalone,
                "tipoDocumento": (
                    "fluxograma"
                    if fluxograma_standalone
                    else "anexo"
                    if anexo_standalone
                    else "procedimento"
                ),
                "identificadorAnexo": identificador_anexo_arquivo,
                "etapaOperacional": etapa_operacional,
            }
        )
    _aplicar_hierarquia_local_do_anexo(resultado)
    _marcar_sufixo_de_interface(resultado)
    return resultado
