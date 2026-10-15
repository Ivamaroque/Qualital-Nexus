"""Regras determinísticas para limpeza e interpretação do texto extraído."""

import re

from app.utils.text_utils import normalize_whitespace, normalized_for_match


_PAGE_RE = re.compile(r"(?:INTERNA\s+)?página\s+\d+\s+de\s+\d+", re.IGNORECASE)
_UNDERSCORE_RE = re.compile(r"^[_\-]{3,}$")
_MEASUREMENT_AFTER_NUMBER_RE = (
    r"(?:%|m[²³23]?|cm[²³23]?|mm|kgf(?:/cm[²2])?|kg|g|l|litros?|"
    r"kpa|mpa|bar|[º°]c)"
)
_IMAGE_ONLY_PAGE_SCALE = 2
_TABLE_IMAGE_SCALE = 2
_TABLE_IMAGE_PADDING = 3
_SECTION_RE = re.compile(
    rf"^(?:\d+\.|\d+\.\d+(?:\.\d+){{0,6}}\.?)(?!\s*{_MEASUREMENT_AFTER_NUMBER_RE}(?=\s|[,.;:]|$))"
    r"\s+(?:[-–—]\s*)?.+",
    re.IGNORECASE,
)
_ITEM_PADRAO_RE = re.compile(
    rf"^\s*(\d+\.(?:\d+\.)*|\d+(?:\.\d+)+)(?!\s*{_MEASUREMENT_AFTER_NUMBER_RE}(?=\s|[,.;:]|$))"
    r"(?=\s|[-–—]|$)",
    re.IGNORECASE,
)
_TABLE_RE = re.compile(
    r"^(?:tabela\s*\d+|quadro\s*\d+|anexo\s+[a-z])\b", re.IGNORECASE
)
_OPERATIONAL_TABLE_SCOPE_RE = re.compile(
    r"\b(?:ETAPAS?|ATIVIDADES?|EXECU[CÇ][AÃ]O|O\s+QUE\s+FAZER)\b",
    re.IGNORECASE,
)
_DEVIATION_TABLE_RESULT_RE = re.compile(r"\bRESULTADOS?\s+ESPERADOS?\b")
_DEVIATION_TABLE_ACTIONS = "ACOES PARA DESVIOS"
_LIST_ITEM_RE = re.compile(
    r"^(?:[•·▪◦*-]|[a-z][)]|\d+[.)-]|\d+\s*[-–—])\s+\S+",
    re.IGNORECASE,
)
_LETTERED_LIST_ITEM_RE = re.compile(
    r"^\s*([a-z])\s*[)]\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_PROCESS_REFERENCE_RE = re.compile(r"^N\d+\s*[-–—]\s+", re.IGNORECASE)
_DOCUMENT_CODE_RE = re.compile(
    r"^(?:PE|PG|PR|PP)-[A-Z0-9]+-\d{5}\b", re.IGNORECASE
)
_ANEXO_DOCUMENTO_RE = re.compile(r"^ANEXO\s+([A-Z]\d*)\b", re.IGNORECASE)
_ANEXO_FILENAME_RE = re.compile(
    r"^\s*ANEXO\s+([A-Z]\d*)\s*(?:[-–—:]\s*(.+?))?\s*(?:\.PDF|\.DOCX?|\.XLSM?)?$",
    re.IGNORECASE,
)
_TABLE_HEADER_RE = re.compile(
    r"^(?:O QUE FAZER|EXECUTANTE|ONDE REGISTRAR|ATIVIDADE|"
    r"ASPECTO/PERIGO|IMPACTO/RISCO|AÇÕES DE CONTROLE)$",
    re.IGNORECASE,
)
_DOCUMENT_METADATA_RE = re.compile(
    r"^(?:"
    r"P\d{1,2}(?:\s*\|\s*P\d{1,2})+"
    r"|INSTALAÇÃO\b|ÁREA\b|DATA\b|RESP(?:ONSÁVEIS)?\b"
    r"|NOME\b|MATR[IÍ]CULA\b|FUNÇÃO\b|GERÊNCIA\b"
    r"|A[CÇ][AÃ]O\s+DE\s+RTA\b"
    r"|\d+\s+DE\s+\d+$"
    r"|(?:SIM|NÃO|NAO|RESP\.?|N\.?A\.?)$"
    r"|[A-Z]\.$"
    r")",
    re.IGNORECASE,
)
_TECHNICAL_MARKER_RE = re.compile(
    r"^(?:objetivo|aplicação|descrição|como fazer|porque fazer|"
    r"registros|definições|recursos necessários|itens críticos)\b",
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
_IMAGE_MARKER_RE = re.compile(r"^\[\[IMAGEM_PDF:(\d+)\]\]$")
_MIN_IMAGE_TOP = 65
_MIN_IMAGE_WIDTH = 120
_MIN_IMAGE_HEIGHT = 80
_MIN_IMAGE_AREA = 15_000
_REPEATED_IMAGE_THRESHOLD = 3
_FIGURE_CAPTION_RE = re.compile(
    r"^[•\-]?\s*FIGURA\s+\d+\s*[-–—:]", re.IGNORECASE
)
_SCREEN_CAPTION_RE = re.compile(r"^TELA\s+\d+\s*[:\-–—]", re.IGNORECASE)
_SPECIAL_BLOCK_START_RE = re.compile(
    r"^(?:LISTA\s+DE\s+VERIFICAÇÃO|OBSERVAÇÕES?\s+(?:PRELIMINARES|\d+)|COMO\s+FAZER|O\s+QUE\s+FAZER"
    r"|RESULTADO\s+ESPERADO|AÇÕES\s+PARA\s+DESVIOS)\s*[:.]?",
    re.IGNORECASE,
)
_NUMBERED_ITEM_RE = re.compile(
    rf"^\s*(\d+(?:\.\d+)*\.?)(?!\s*{_MEASUREMENT_AFTER_NUMBER_RE}(?=\s|[,.;:]|$))"
    r"(?=\s|[-–—]|$)\s*(?:[-–—]\s*)?(.*)$",
    re.IGNORECASE,
)
_ANEXO_ALPHANUMERIC_HEADING_RE = re.compile(
    r"^\s*(\d+[A-Z])\s*[-–—]\s*(.+)$",
    re.IGNORECASE,
)
_ACTION_IMPERATIVE_RE = re.compile(
    r"\b(?:aborte|abortar|acompanhe|acompanhar|acople|acoplar|abra|abrir|acione|acionar|"
    r"aguarde|aguardar|alinhe|alinhar|anote|anotar|aperte|apertar|baixe|baixar|clique|clicar|"
    r"comunique|comunicar|confirme|confirmar|digite|digitar|escolha|escolher|feche|fechar|informe|informar|"
    r"inspecione|inspecionar|instale|instalar|interrompa|interromper|isole|isolar|ligue|ligar|"
    r"mantenha|manter|observe|observar|pe[cç]a|pedir|posicione|posicionar|preencha|preencher|realize|realizar|recoloque|recolocar|"
    r"pare|parar|parta|partir|regule|regular|retorne|retornar|retire|retirar|selecione|selecionar|solicite|solicitar|suba|subir|teste|testar|trave|travar|"
    r"use|usar|utilize|utilizar|verifique|verificar|certifique|certificar|varie|variar)\b",
    re.IGNORECASE,
)
_OPERATIONAL_RESPONSIBLE_CELL_RE = re.compile(
    r"^(?:RESP\.?|OP[- ]?[A-Z0-9]+|CIOP(?:-[A-Z0-9]+)?|"
    r"FSO(?:[- ]CIMA)?|BARCO\s+DE\s+APOIO)$",
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
_OPERATIONAL_TABLE_ROW_RE = re.compile(
    r"^\s*PASSO\s+(\d+)\s*\|\s*(.+)$", re.IGNORECASE | re.DOTALL
)
_OPERATIONAL_STAGE_RE = re.compile(
    r"^\s*ETAPA\s+(\d+)\s*[-–—:]\s*(.+)$", re.IGNORECASE
)
_SUMARIO_TITULOS = {
    "OBJETIVO",
    "APLICAÇÃO",
    "DESCRIÇÃO",
    "REGISTROS",
    "DEFINIÇÕES",
}
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
    r"^\s*(?:\d+(?:\.\d+)+\.?\s+)?(?:abortar|abrir|acessar|acionar|acompanhar|acoplar|aguardar|ajustar|"
    r"alinhar|amarrar|anotar|aplicar|aproximar|atentar|atuar|avaliar|avisar|bloquear|certificar|checar|coletar|colocar|comunicar|confirmar|"
    r"contatar|desligar|emitir|encaminhar|entrar\s+em\s+contato|estabelecer|executar|"
    r"desconectar|despressurizar|dirigir-se|efetuar|elevar|etiquetar|fechar|ficar|garantir|indicar|informar|iniciar|inspecionar|instalar|interromper|isolar|"
    r"lacrar|ler|levar|liberar|ligar|manter|medir|monitorar|normalizar|obter|operar|orientar|pagar|parar|partir|pedir|posicionar|preencher|pressurizar|puxar|"
    r"proceder|realizar|receber|registrar|regular|remover|reparar|restabelecer|retirar|selecionar|seguir|sinalizar|solicitar|"
    r"tomar|transportar|trocar|usar|utilizar|verificar|visualizar)\b",
    re.IGNORECASE,
)
_OBSERVATION_RE = re.compile(
    r"^OBS(?:ERVA(?:ÇÃO|CAO))?\s*:",
    re.IGNORECASE,
)
_NOTICE_RE = re.compile(
    r"^(?:OBS(?:ERVA(?:ÇÃO|CAO))?|NOTA|ATENÇÃO)\s*\d*\.?\s*:",
    re.IGNORECASE,
)
_TABLE_EXECUTOR_MARKER_RE = re.compile(
    r"\s*\[\[EXECUTANTE_TABELA:(?P<executante>[^\]]+)\]\]\s*",
    re.IGNORECASE,
)
_TABLE_REGISTER_SUFFIX_RE = re.compile(
    r"^(?P<executante>.+?)\s+(?:APLAT|CPROP|BDOC|SAP)(?:\s+E\s+(?:APLAT|CPROP|BDOC|SAP))*$",
    re.IGNORECASE,
)
_ACTION_CUE_RE = re.compile(
    r"\b(?:dever[aá]|dever[aã]o|deve-se|devem-se|deve|devem|recomenda-se|abortar|abrir|aguardar|isolar|ligar|"
    r"realizar|solicitar|bloquear|acionar|"
    r"informar\s+imediatamente|entrar\s+em\s+contato|parar\s+os?|alinhar\s+para|"
    r"estabelecer\s+(?:a\s+)?comunica[cç][aã]o|confirmar\s+que|avaliar\s+(?:o|a)|"
    r"coletar\s+(?:uma|a)|tomar\s+as\s+a[cç][oõ]es|informar\s+(?:ao|a|o)|"
    r"s[oó]\s+abrir|abrir\s+novo\s+registro)\b",
    re.IGNORECASE,
)
_NEGATIVE_ACTION_RE = re.compile(
    r"\bn[aã]o\s+dev(?:e|em|er[aá]|er[aã]o)\b", re.IGNORECASE
)
_FINITE_OPERATIONAL_ACTION_RE = re.compile(
    r"\b(?:acompanha|abre|aciona|amarra|aproxima|avisa|certifica-se|coleta|coloca|confirma|continua|"
    r"desliga|define|emite|entrega|etiqueta|faz|fecha|garante|informa|inicia|interrompe|lacra|leva|libera|liga|"
    r"monitora|normaliza|obt[eé]m|orienta|parte|pede|posiciona|recolhe|registra|regula|reinicia|realiza|"
    r"seleciona|solicita|toma|troca-se|verifica)\b",
    re.IGNORECASE,
)
_REQUIRED_RESOURCE_RE = re.compile(
    r"^Para\s+.+?,\s+s[aã]o\s+necess[aá]ri[oa]s?\s+.+",
    re.IGNORECASE,
)
_FUNDAMENTAL_REQUIREMENT_RE = re.compile(
    r"^[ÉE]\s+fundamental\s+(?:uma\s+)?(?:perfeita\s+|adequada\s+)?comunica[cç][aã]o\b.+",
    re.IGNORECASE,
)
_NECESSITY_ACTION_RE = re.compile(
    r"\b(?:precisa(?:m)?|necessita(?:m)?)\s+"
    r"(?:desligar|executar|fazer|informar|realizar|solicitar|verificar)\b",
    re.IGNORECASE,
)
_ACTIONABLE_PASSIVE_RE = re.compile(
    r"\b(?:dev(?:e|em|er[aá]|er[aã]o)|pod(?:e|em|er[aá]|er[aã]o))\s+ser\s+"
    r"(?:acionad|avaliad|bloquead|colocad|comunicad|dad|desligad|emitid|lan[cç]ad|mantid|mobilizad|"
    r"parad|preenchid|realizad|registrad|solicitad|tomad)[oa]s?\b",
    re.IGNORECASE,
)


def _is_image_marker(texto: str) -> bool:
    return _IMAGE_MARKER_RE.fullmatch(normalize_whitespace(texto)) is not None


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
        if (
            linha in {"_", "."}
            or normalizada == "INTERNA"
            or _UNDERSCORE_RE.match(linha)
        ):
            continue
        if _NOISE_LINE_RE.match(linha):
            continue
        if normalizada.startswith(
            (
                "APROVADO POR",
                "GERIDO POR",
                "GESTÃO DO DOCUMENTO",
                "GESTAO DO DOCUMENTO",
            )
        ):
            continue
        if (
            linhas_limpas
            and re.search(r"\b[A-Z]{1,8}-$", linhas_limpas[-1])
            and re.match(r"^[A-Z0-9]", linha)
        ):
            linhas_limpas[-1] = f"{linhas_limpas[-1]}{linha}"
            continue
        linhas_limpas.append(linha)
    return "\n".join(linhas_limpas).strip()


def detectar_categoria(texto: str) -> str:
    normalizado = normalized_for_match(texto)
    primeira_linha = texto.splitlines()[0] if texto else ""
    if _is_image_marker(primeira_linha):
        return "imagem"
    if _FIGURE_CAPTION_RE.match(primeira_linha) or _SCREEN_CAPTION_RE.match(
        primeira_linha
    ):
        return "legenda_figura"
    if _NOTICE_RE.match(primeira_linha):
        return "aviso_informativo"
    if normalizado.rstrip(".:") == "LISTA DE VERIFICACAO":
        return "lista_verificacao"
    texto_sem_item = re.sub(
        r"^\s*\d+(?:\.\d+)*\.?\s*(?:[-–—]\s*)?", "", normalizado
    )
    if _DOCUMENT_METADATA_RE.match(normalizado):
        return "fragmento_interface"
    if _DOCUMENT_CODE_RE.match(primeira_linha):
        return "padrao_documento"
    if _ANEXO_DOCUMENTO_RE.match(primeira_linha.strip()):
        return "anexo_documento"
    if (
        _TABLE_HEADER_RE.match(primeira_linha)
        or all(
            termo in normalizado
            for termo in ("O QUE FAZER", "EXECUTANTE", "ONDE REGISTRAR")
        )
        or all(
            termo in normalizado
            for termo in ("ATIVIDADE", "ASPECTO/PERIGO", "ACOES DE CONTROLE")
        )
        or normalizado == "QUEM O QUE"
    ):
        return "cabecalho_tabela"
    if re.match(
        r"^FIGURA\s*\d+\s*[-–—:]\s*DETALHAMENTO\s+DAS\s+ATIVIDADES",
        normalizado,
    ):
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
    if (
        _DEVIATION_TABLE_RESULT_RE.search(normalizado)
        and _DEVIATION_TABLE_ACTIONS in normalizado
    ):
        return "tabela_desvios"
    anexo = _ANEXO_DOCUMENTO_RE.match(primeira_linha.strip())
    if anexo:
        return f"anexo_{anexo.group(1).lower()}"
    if normalizado.startswith("ANEXO"):
        return "anexo"
    tabela = re.match(r"^TABELA\s*(\d+)\b", normalizado)
    if tabela and tabela.group(1) == "2":
        return (
            "tabela_2"
            if _OPERATIONAL_TABLE_SCOPE_RE.search(normalizado)
            else "tabelas_tecnicas"
        )
    if tabela and tabela.group(1) == "5":
        return "tabela_5"
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
    """Distingue uma seção de uma atividade numerada de tabela."""
    primeira_linha = texto.splitlines()[0] if texto else ""
    if re.match(r"^\d+(?:\.\d+)+\.?\s*[-–—]", primeira_linha):
        return True
    if re.match(r"^\d+(?:\.\d+){2,}\.?\s+\S+", primeira_linha):
        return True
    item_alfabetico = _LETTERED_LIST_ITEM_RE.match(primeira_linha)
    if item_alfabetico and (
        _ACTION_START_RE.match(item_alfabetico.group(2))
        or _FINITE_OPERATIONAL_ACTION_RE.search(item_alfabetico.group(2))
        or _ACTION_IMPERATIVE_RE.search(item_alfabetico.group(2))
    ):
        return True
    return (
        re.fullmatch(
            r"\d+\.\s+(?:OBJETIVO|APLICAÇÃO|DESCRIÇÃO|REGISTROS|DEFINIÇÕES)",
            primeira_linha.strip(),
            re.IGNORECASE,
        )
        is not None
    )


def extrair_palavras_chave(texto: str) -> list[str]:
    normalizado = normalized_for_match(texto)
    termos = (
        "objetivo",
        "aplicação",
        "descrição",
        "tabela",
        "como fazer",
        "porque fazer",
        "anexo",
        "registro",
        "execução",
        "atividade",
        "recursos",
        "itens críticos",
        "ações de controle",
        "p.p.n.t",
        "boletim",
    )
    return [
        termo for termo in termos if normalized_for_match(termo) in normalizado
    ]


def extrair_item_padrao(texto: str) -> str:
    primeira_linha = texto.splitlines()[0] if texto else ""
    resultado = _ITEM_PADRAO_RE.match(primeira_linha)
    return resultado.group(1) if resultado else ""


def _eh_titulo_de_sumario(bloco: list[str]) -> bool:
    if len(bloco) != 1:
        return False
    titulo = normalize_whitespace(bloco[0])
    return (
        bool(re.fullmatch(r"\d+\.\s+.+", titulo))
        and titulo.split(maxsplit=1)[1] in _SUMARIO_TITULOS
    )


def _remover_sumario_inicial(blocos: list[list[str]]) -> list[list[str]]:
    """Remove o sumário quando suas seções reaparecem com conteúdo."""
    indice_inicial = next(
        (
            indice
            for indice, bloco in enumerate(blocos)
            if _eh_titulo_de_sumario(bloco)
        ),
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
    if len(blocos) < 2 or not _DOCUMENT_CODE_RE.match(
        normalize_whitespace(blocos[0][0])
    ):
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


def _linha_numerada_e_instrucao(
    linha: str, tem_subitens: bool, resumo_anexo: bool
) -> bool:
    """Distingue passos operacionais de títulos hierárquicos."""
    correspondencia = _NUMBERED_ITEM_RE.match(normalize_whitespace(linha))
    if (
        not correspondencia
        or tem_subitens
        or _ANEXO_OPERATIONAL_HEADING_RE.match(linha)
    ):
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
        "ALT",
        "CONFIG",
        "FLOW COMP",
        "LIST",
        "METER",
        "OBS",
        "USER",
        "VALOR TOTALIZADO DO GAS",
    }:
        return True
    if texto.lstrip().startswith(".:"):
        return True
    palavras = normalizado.split()
    letras_isoladas = sum(len(palavra) == 1 for palavra in palavras)
    return len(palavras) >= 4 and letras_isoladas / len(palavras) >= 0.5


def _marcar_sufixo_de_interface(blocos: list[dict]) -> None:
    """Descarta OCR de telas quando ele forma um sufixo isolado."""
    inicio = next(
        (
            indice
            for indice in range(len(blocos) - 1, -1, -1)
            if blocos[indice].get("categoria")
            == "cabecalho_documento_repetido"
        ),
        len(blocos),
    )
    sufixo = blocos[inicio:]
    if len(sufixo) < 5:
        return
    fragmentos = sum(
        _parece_fragmento_interface(str(bloco.get("texto") or ""))
        for bloco in sufixo
    )
    if fragmentos / len(sufixo) < 0.5:
        return
    tem_estrutura_documental = any(
        bloco.get("itemPadraoDetectado")
        or bloco.get("categoria")
        in {"instrucao_operacional", "secao_principal", "subsecao_numerada"}
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
    return (
        correspondencia.group(2).lstrip("-–— ").strip()
        if correspondencia
        else ""
    )


def _conteudo_em_caixa_alta(texto: str) -> bool:
    conteudo = _conteudo_item_numerado(texto)
    letras = [caractere for caractere in conteudo if caractere.isalpha()]
    maiusculas = sum(caractere.isupper() for caractere in letras)
    return bool(letras) and maiusculas / len(letras) >= 0.9


def _formatar_item_local_do_anexo(
    item_pai: str, item_local: str, escopo: str
) -> str:
    pai = item_pai.rstrip(".")
    local = item_local.strip().strip("()").rstrip(".")
    separador = "" if pai[-1:].isalpha() else "."
    return _formatar_item_do_anexo(f"{pai}{separador}({local}.)", escopo)


def _aplicar_hierarquia_local_do_anexo(blocos: list[dict]) -> None:
    """Reconstrói a numeração das listas automáticas do Word."""
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
            bloco["itemPadraoDetectado"] = _formatar_item_do_anexo(
                item_pai, str(bloco.get("escopo"))
            )
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
            if (
                eh_titulo_estrutural
                and bloco.get("categoria") == "item_numerado_anexo"
            ):
                bloco["categoria"] = "subsecao_numerada"
            elif not eh_titulo_estrutural:
                bloco["categoria"] = "item_numerado_anexo"
            bloco["tituloEstrutural"] = eh_titulo_estrutural
            bloco["secaoContextual"] = _formatar_item_do_anexo(
                item_fonte, str(bloco.get("escopo"))
            )
            continue

        if (
            normalized_for_match(texto).rstrip(".") == "PROCEDIMENTO"
            and item_pai
        ):
            em_procedimento = True
            contador_local = 0
            bloco["categoria"] = "geral"
            bloco["tituloEstrutural"] = False
            bloco["secaoContextual"] = _formatar_item_do_anexo(
                item_pai, str(bloco.get("escopo"))
            )
            continue

        if (
            not em_procedimento
            or not item_pai
            or texto.upper().startswith("OBS")
        ):
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

        bloco["secaoContextual"] = _formatar_item_do_anexo(
            item_pai, str(bloco.get("escopo"))
        ).rstrip(".")
        texto_sem_item = _conteudo_item_numerado(texto) or texto
        item_local_com_filhos = bool(
            item_fonte
            and bloco.get("temSubitens")
            and len(item_fonte.rstrip(".").split(".")) == 1
            and re.search(
                r"\b(?:como\s+segue|seguintes\s+passos)\b",
                texto_sem_item,
                re.IGNORECASE,
            )
        )
        bloco["tituloEstrutural"] = item_local_com_filhos
        if item_local_com_filhos:
            bloco["categoria"] = "secao_principal"
        elif normalized_for_match(texto_sem_item).startswith(
            ("SE NAO", "NAO HAVENDO")
        ):
            bloco["categoria"] = "geral"
        else:
            bloco["categoria"] = "instrucao_operacional"
            bloco["acaoUnica"] = True


def _bloco_e_lista_numerada(bloco: list[str]) -> bool:
    return bool(bloco) and all(
        _NUMBERED_LIST_ITEM_RE.match(normalize_whitespace(linha))
        for linha in bloco
    )


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
    """Identifica checklists que devem permanecer em uma célula."""
    if not _bloco_e_lista_visual(bloco):
        return False
    return re.search(r"\.{3,}", normalize_whitespace(bloco[0])) is not None


def _deve_unir_continuacao(bloco: list[str], seguinte: list[str]) -> bool:
    if not bloco or not seguinte:
        return False
    if _is_image_marker(bloco[0]) or _is_image_marker(seguinte[0]):
        return False
    anterior = normalize_whitespace(bloco[-1])
    proxima = normalize_whitespace(seguinte[0])
    if not anterior or not proxima:
        return False
    if _LETTERED_LIST_ITEM_RE.match(proxima):
        return False
    # Em PDFs paginados, a quebra pode ocorrer entre a palavra "figura" e o
    # número seguido da continuação da frase. Esse "5." não é um novo item.
    if re.search(r"\bfigura\s*$", anterior, re.IGNORECASE) and re.match(
        r"^\d+\.\s+\S+", proxima
    ):
        return True
    if _SECTION_RE.match(proxima):
        return False
    proxima_e_tabela = _TABLE_RE.match(proxima) is not None
    if proxima_e_tabela:
        # Uma quebra visual pode cair exatamente antes de uma referência a
        # tabela/figura, sem que isso represente um novo título.
        if anterior.lower().endswith(
            (" na", " no", " à", " ao", " pela", " pelo")
        ):
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
    if anterior.endswith("-") or (
        anterior.endswith((",", ";")) and proxima[:1].islower()
    ):
        return True
    # PDFs frequentemente quebram códigos/equipamentos de um mesmo item
    # em outro bloco. Enquanto a frase estiver aberta, preserve a célula.
    if (
        _LIST_ITEM_RE.match(normalize_whitespace(bloco[0]))
        and not _SECTION_RE.match(normalize_whitespace(bloco[0]))
        and not _LIST_ITEM_RE.match(proxima)
        and anterior[-1] not in ".!?;"
    ):
        return True
    inicia_continuacao = proxima[0].islower() or proxima.upper().startswith(
        ("PSIG ", "KGF/", "CM2 ")
    )
    termina_aberto = (
        anterior.endswith((",", ";", ":", " e", " ou"))
        or anterior[-1] not in ".!?"
    )
    return inicia_continuacao and termina_aberto


def _agrupar_fragmentos_logicos(
    blocos: list[list[str]],
    agrupar_listas_visuais: bool = True,
) -> list[list[str]]:
    """Reconstrói listas, tabelas e frases quebradas."""
    agrupados: list[list[str]] = []
    indice = 0
    while indice < len(blocos):
        atual = list(blocos[indice])

        if _bloco_e_lista_pontilhada(atual):
            indice += 1
            while (
                indice < len(blocos)
                and _bloco_e_lista_pontilhada(blocos[indice])
                and sum(len(linha) + 1 for linha in [*atual, *blocos[indice]])
                <= _MAX_GROUPED_TABLE_CHARACTERS
            ):
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        if _bloco_e_lista_numerada(atual):
            indice += 1
            while indice < len(blocos) and _bloco_e_lista_numerada(
                blocos[indice]
            ):
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
                and sum(len(linha) + 1 for linha in [*atual, *blocos[indice]])
                <= _MAX_GROUPED_TABLE_CHARACTERS
            ):
                atual.extend(blocos[indice])
                indice += 1
            while (
                indice < len(blocos)
                and not _is_image_marker(
                    blocos[indice][0] if blocos[indice] else ""
                )
                and _deve_unir_continuacao(atual, blocos[indice])
            ):
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        primeira = normalize_whitespace(atual[0]) if atual else ""
        if _TECHNICAL_GROUP_HEADER_RE.match(primeira):
            indice += 1
            while indice < len(blocos):
                proxima = (
                    normalize_whitespace(blocos[indice][0])
                    if blocos[indice]
                    else ""
                )
                if _TECHNICAL_GROUP_HEADER_RE.match(proxima):
                    break
                if not _TECHNICAL_PARAMETER_RE.match(
                    proxima
                ) and not _deve_unir_continuacao(atual, blocos[indice]):
                    break
                atual.extend(blocos[indice])
                indice += 1
            agrupados.append(atual)
            continue

        indice += 1
        while indice < len(blocos) and _deve_unir_continuacao(
            atual, blocos[indice]
        ):
            atual.extend(blocos[indice])
            indice += 1
        agrupados.append(atual)
    return agrupados


def _texto_tem_acoes_explicitas(texto: str) -> bool:
    sem_negativas = _NEGATIVE_ACTION_RE.sub("", texto)
    conteudo = re.sub(
        r"^\s*(?:[•·▪◦*\-]|[a-z][)])\s*",
        "",
        sem_negativas,
        flags=re.IGNORECASE,
    )
    if (
        _ACTION_START_RE.match(conteudo)
        or _ACTION_IMPERATIVE_RE.search(conteudo)
        or _tem_acao_finita_operacional(conteudo)
        or _REQUIRED_RESOURCE_RE.match(conteudo)
        or _FUNDAMENTAL_REQUIREMENT_RE.match(conteudo)
        or _NECESSITY_ACTION_RE.search(conteudo)
        or _ACTIONABLE_PASSIVE_RE.search(conteudo)
    ):
        return True
    normalizado = normalized_for_match(conteudo)
    if (
        "DEVE-SE SEGUIR" in normalizado
        or "RECOMENDA-SE COLETAR" in normalizado
    ):
        return True
    return len(_ACTION_CUE_RE.findall(sem_negativas)) >= 2


def _tem_acao_finita_operacional(texto: str) -> bool:
    sujeitos_humanos = re.compile(
        r"\b(?:equipe|executante|marinheiro|oficial|operador|supervis[aã]o|t[eé]cnic[oa])\b",
        re.IGNORECASE,
    )
    for correspondencia in _FINITE_OPERATIONAL_ACTION_RE.finditer(texto):
        prefixo = texto[: correspondencia.start()]
        prefixo_sentenca = re.split(r"[.!?]", prefixo)[-1]
        if not prefixo_sentenca.strip() or sujeitos_humanos.search(
            prefixo_sentenca
        ):
            return True
    return False


def _item_numerado_tem_acao_explicita(texto: str) -> bool:
    sem_negativas = _NEGATIVE_ACTION_RE.sub("", texto)
    passiva = re.search(
        r"\bdev(?:e|em|er[aá]|er[aã]o)\s+ser\s+[\wÀ-ÿ-]+",
        sem_negativas,
        re.IGNORECASE,
    )
    if passiva:
        return _ACTIONABLE_PASSIVE_RE.search(sem_negativas) is not None
    return _ACTION_CUE_RE.search(sem_negativas) is not None


def _juntar_linhas_do_bloco(linhas: list[str]) -> str:
    """Remove quebras visuais e mantém listas na mesma célula."""
    linhas_logicas: list[str] = []
    for linha in linhas:
        trecho = normalize_whitespace(linha)
        if not trecho:
            continue
        if (
            linhas_logicas
            and re.search(r"\bfigura\s*$", linhas_logicas[-1], re.IGNORECASE)
            and re.match(r"^\d+\.\s+\S+", trecho)
        ):
            linhas_logicas[-1] = f"{linhas_logicas[-1]} {trecho}".strip()
            continue
        elif linhas_logicas and (
            _is_image_marker(trecho)
            or _FIGURE_CAPTION_RE.match(trecho)
            or _SPECIAL_BLOCK_START_RE.match(trecho)
        ):
            linhas_logicas.append(trecho)
            continue
        if _LIST_ITEM_RE.match(trecho) and linhas_logicas:
            linhas_logicas.append(trecho)
        elif linhas_logicas:
            linhas_logicas[-1] = f"{linhas_logicas[-1]} {trecho}".strip()
        else:
            linhas_logicas.append(trecho)
    return re.sub(
        r"\b([A-Z]{1,8})-\s+(?=[A-Z0-9])",
        r"\1-",
        "\n".join(linhas_logicas),
    )
