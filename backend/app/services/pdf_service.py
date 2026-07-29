import re

import fitz

from app.utils.text_utils import normalize_whitespace, normalized_for_match


_PAGE_RE = re.compile(r"^página\s+\d+\s+de\s+\d+\s*$", re.IGNORECASE)
_UNDERSCORE_RE = re.compile(r"^[_\-]{3,}$")
_SECTION_RE = re.compile(r"^\d+(?:\.\d+){0,4}\.?\s+.+")
_TABLE_RE = re.compile(r"^(?:tabela\s*\d+|quadro\s*\d+|anexo\s+[a-z])\b", re.IGNORECASE)
_TECHNICAL_MARKER_RE = re.compile(
    r"^(?:objetivo|aplicação|descrição|como fazer|porque fazer|registros|definições|recursos necessários|itens críticos)\b",
    re.IGNORECASE,
)


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrai texto página a página de um PDF que contenha camada textual."""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            return "\n\n".join(page.get_text("text", sort=True) for page in document)
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise ValueError("Não foi possível extrair texto do PDF.") from exc


def limpar_texto_pdf(texto: str) -> str:
    linhas_limpas: list[str] = []
    for linha in texto.splitlines():
        linha = normalize_whitespace(linha)
        normalizada = normalized_for_match(linha)
        if not linha or normalizada == "INTERNA" or _PAGE_RE.match(linha) or _UNDERSCORE_RE.match(linha):
            continue
        if normalizada.startswith(("APROVADO POR", "GERIDO POR", "GESTÃO DO DOCUMENTO", "GESTAO DO DOCUMENTO")):
            continue
        linhas_limpas.append(linha)
    return "\n".join(linhas_limpas)


def detectar_categoria(texto: str) -> str:
    normalizado = normalized_for_match(texto)
    categorias = (
        ("objetivo", "objetivo"),
        ("aplicacao", "aplicação"),
        ("como_fazer", "como fazer"),
        ("porque_fazer", "porque fazer"),
        ("registros", "registro"),
        ("definicoes", "definiç"),
        ("recursos_necessarios", "recursos necessários"),
        ("itens_criticos", "itens críticos"),
        ("anexo", "anexo"),
    )
    for categoria, termo in categorias:
        if normalized_for_match(termo) in normalizado:
            return categoria
    if re.search(r"^\s*\d+(?:\.\d+)+", texto):
        return "subsecao_numerada"
    if _TABLE_RE.match(texto):
        return "titulo_tabela"
    if "ATIVIDADE" in normalizado:
        return "atividade_tabela"
    if _SECTION_RE.match(texto):
        return "secao_principal"
    return "geral"


def detectar_escopo(texto: str) -> str:
    normalizado = normalized_for_match(texto)
    if "ANEXO A" in normalizado:
        return "anexo_a"
    if "ANEXO B" in normalizado:
        return "anexo_b"
    if "ANEXO" in normalizado:
        return "anexo"
    tabela = re.search(r"\bTABELA\s*(\d+)\b", normalizado)
    if tabela and tabela.group(1) in {"2", "5"}:
        return f"tabela_{tabela.group(1)}"
    if "TABELA" in normalizado or "QUADRO" in normalizado:
        return "tabelas_tecnicas"
    return "documento_principal" if _SECTION_RE.match(texto) else "geral"


def extrair_palavras_chave(texto: str) -> list[str]:
    normalizado = normalized_for_match(texto)
    termos = (
        "objetivo", "aplicação", "descrição", "tabela", "como fazer", "porque fazer",
        "anexo", "registro", "execução", "atividade", "recursos", "itens críticos",
        "ações de controle", "p.p.n.t", "boletim",
    )
    return [termo for termo in termos if normalized_for_match(termo) in normalizado]


def separar_blocos(texto: str) -> list[dict]:
    """Agrupa seções e marcadores técnicos sem alterar a ordem do documento."""
    blocos: list[list[str]] = []
    atual: list[str] = []
    for linha in texto.splitlines():
        inicio_de_bloco = bool(_SECTION_RE.match(linha) or _TABLE_RE.match(linha) or _TECHNICAL_MARKER_RE.match(linha))
        if inicio_de_bloco and atual:
            blocos.append(atual)
            atual = []
        atual.append(linha)
    if atual:
        blocos.append(atual)

    resultado: list[dict] = []
    escopo_contextual = "geral"
    escopos_explicitos = {"anexo", "anexo_a", "anexo_b", "tabela_2", "tabela_5", "tabelas_tecnicas"}
    for ordem, linhas in enumerate(blocos, start=1):
        bloco_texto = "\n".join(linhas).strip()
        if not bloco_texto:
            continue
        escopo_detectado = detectar_escopo(bloco_texto)
        if escopo_detectado in escopos_explicitos:
            escopo_contextual = escopo_detectado
        resultado.append(
            {
                "ordem": ordem,
                "texto": bloco_texto,
                "categoria": detectar_categoria(bloco_texto),
                "escopo": escopo_contextual if escopo_contextual != "geral" else escopo_detectado,
                "palavras_chave": extrair_palavras_chave(bloco_texto),
            }
        )
    return resultado
