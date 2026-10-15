"""Extrai texto, tabelas e imagens de PDFs usando PyMuPDF."""

import base64
import re
from collections import Counter

import fitz

from app.services.pdf_text_service import (
    _ACTION_START_RE,
    _ATIVIDADE_TABELA_RE,
    _DEVIATION_TABLE_ACTIONS,
    _DEVIATION_TABLE_RESULT_RE,
    _IMAGE_MARKER_RE,
    _IMAGE_ONLY_PAGE_SCALE,
    _LIST_ITEM_RE,
    _MIN_IMAGE_AREA,
    _MIN_IMAGE_HEIGHT,
    _MIN_IMAGE_TOP,
    _MIN_IMAGE_WIDTH,
    _OPERATIONAL_TABLE_ROW_RE,
    _REPEATED_IMAGE_THRESHOLD,
    _TABLE_EXECUTOR_MARKER_RE,
    _TABLE_IMAGE_PADDING,
    _TABLE_IMAGE_SCALE,
    _is_image_marker,
    _juntar_linhas_do_bloco,
)
from app.utils.text_utils import normalize_whitespace, normalized_for_match


def _bboxes_se_sobrepoem(
    primeiro: tuple[float, ...], segundo: tuple[float, ...]
) -> bool:
    if len(primeiro) != 4 or len(segundo) != 4:
        return False
    return not (
        primeiro[2] <= segundo[0]
        or segundo[2] <= primeiro[0]
        or primeiro[3] <= segundo[1]
        or segundo[3] <= primeiro[1]
    )


def _linha_dentro_de_tabela(
    linha_bbox: tuple[float, float, float, float],
    tabela_bbox: tuple[float, ...],
) -> bool:
    centro_x = (linha_bbox[0] + linha_bbox[2]) / 2
    centro_y = (linha_bbox[1] + linha_bbox[3]) / 2
    return (
        tabela_bbox[0] <= centro_x <= tabela_bbox[2]
        and tabela_bbox[1] <= centro_y <= tabela_bbox[3]
    )


def _normalizar_celula_tabela(valor: object) -> str:
    if valor is None:
        return ""
    return _juntar_linhas_do_bloco(str(valor).splitlines())


def _linhas_formam_tabela_operacional(linhas: list[list[object]]) -> bool:
    if not linhas:
        return False
    cabecalho_normalizado = normalized_for_match(
        " ".join(str(celula or "") for celula in linhas[0])
    )
    if (
        _DEVIATION_TABLE_RESULT_RE.search(cabecalho_normalizado)
        and _DEVIATION_TABLE_ACTIONS in cabecalho_normalizado
    ):
        return True
    return (
        any(
            any(
                marcador in normalized_for_match(celula or "")
                for celula in linha
                for marcador in ("O QUE FAZER", "PASSO")
            )
            and any(
                "DESCRICAO" in normalized_for_match(celula or "")
                for celula in linha
            )
            for linha in linhas
        )
        or any(
            len(linha) >= 2
            and str(linha[0] or "").strip().isdigit()
            and _ACTION_START_RE.match(str(linha[1] or "").strip()) is not None
            for linha in linhas
        )
        or any(
            len(linha) == 3
            and bool(linha[0])
            and (
                _ATIVIDADE_TABELA_RE.match(str(linha[0]))
                or normalized_for_match(str(linha[0])).startswith(
                    ("COMO FAZER", "PORQUE FAZER")
                )
            )
            for linha in linhas
        )
    )


def _serializar_tabela_operacional_para_parser(tabela: object) -> str:
    partes = re.split(
        r"\n\s*\n", _serializar_tabela(tabela, incluir_executante=True)
    )
    selecionadas = []
    for parte in partes:
        trecho = parte.strip()
        normalizado = normalized_for_match(trecho)
        if (
            normalizado == "O QUE FAZER EXECUTANTE ONDE REGISTRAR"
            or _ATIVIDADE_TABELA_RE.match(trecho)
            or _OPERATIONAL_TABLE_ROW_RE.match(trecho)
            or normalizado.startswith(("COMO FAZER", "PORQUE FAZER"))
        ):
            selecionadas.append(trecho)
    return "\n\n".join(selecionadas)


def _recortar_tabela_como_png(
    page: fitz.Page, tabela: object
) -> tuple[bytes, int, int] | None:
    try:
        area = fitz.Rect(tabela.bbox)
        area.x0 = max(page.rect.x0, area.x0 - _TABLE_IMAGE_PADDING)
        area.y0 = max(page.rect.y0, area.y0 - _TABLE_IMAGE_PADDING)
        area.x1 = min(page.rect.x1, area.x1 + _TABLE_IMAGE_PADDING)
        area.y1 = min(page.rect.y1, area.y1 + _TABLE_IMAGE_PADDING)
        if area.width <= 0 or area.height <= 0:
            return None
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(_TABLE_IMAGE_SCALE, _TABLE_IMAGE_SCALE),
            clip=area,
            alpha=False,
        )
        return pixmap.tobytes("png"), pixmap.width, pixmap.height
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _serializar_tabela(
    tabela: object, *, incluir_executante: bool = False
) -> str:
    linhas = [list(linha) for linha in tabela.extract()]
    cabecalho_normalizado = (
        normalized_for_match(
            " ".join(str(celula or "") for celula in linhas[0])
        )
        if linhas
        else ""
    )
    tabela_de_desvios = bool(
        _DEVIATION_TABLE_RESULT_RE.search(cabecalho_normalizado)
        and _DEVIATION_TABLE_ACTIONS in cabecalho_normalizado
    )
    if tabela_de_desvios:
        serializadas: list[str] = []
        for indice_linha, linha in enumerate(linhas):
            celulas = [_normalizar_celula_tabela(celula) for celula in linha]
            if not any(celulas):
                continue
            if indice_linha == 0:
                serializadas.append("RESULTADO ESPERADO | AÇÕES PARA DESVIOS")
                continue
            resultado_esperado = celulas[0] if celulas else ""
            acao_desvio = celulas[1] if len(celulas) > 1 else ""
            if resultado_esperado or acao_desvio:
                serializadas.append(
                    f"RESULTADO ESPERADO | {resultado_esperado}\n"
                    f"AÇÕES PARA DESVIOS | {acao_desvio}"
                )
        return "\n\n".join(serializadas)

    cabecalho_responsabilidade = bool(linhas) and all(
        termo
        in normalized_for_match(
            " ".join(str(celula or "") for celula in linhas[0])
        )
        for termo in ("QUEM", "O QUE")
    )
    if cabecalho_responsabilidade:
        linhas_agrupadas: list[list[object]] = [linhas[0]]
        for linha in linhas[1:]:
            apenas_executante = bool(linha and linha[0]) and not any(linha[1:])
            anterior_tem_execucao = (
                len(linhas_agrupadas) > 1
                and len(linhas_agrupadas[-1]) >= 2
                and bool(linhas_agrupadas[-1][1])
            )
            if apenas_executante and anterior_tem_execucao:
                linhas_agrupadas[-1][0] = (
                    f"{linhas_agrupadas[-1][0]}; {linha[0]}"
                )
                continue
            linhas_agrupadas.append(linha)
        linhas = linhas_agrupadas
    operacional = _linhas_formam_tabela_operacional(linhas)

    serializadas: list[str] = []
    descricao_antecipada = ""
    for indice_linha, linha in enumerate(linhas):
        preservar_lista = (
            not operacional
            and len(linhas) == 1
            and any(
                _LIST_ITEM_RE.search(str(celula or "")) for celula in linha
            )
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
            if normalizada == "PASSO" and any(
                "DESCRICAO" in normalized_for_match(celula)
                for celula in celulas
            ):
                continue
            if not primeira and celulas[1] and indice_linha + 1 < len(linhas):
                proxima = [
                    _normalizar_celula_tabela(celula)
                    for celula in linhas[indice_linha + 1]
                ]
                if (
                    proxima
                    and proxima[0].isdigit()
                    and (len(proxima) < 2 or not proxima[1])
                ):
                    descricao_antecipada = celulas[1]
                    continue
            if primeira.isdigit() and (celulas[1] or descricao_antecipada):
                serializadas.append(
                    f"PASSO {primeira} | {celulas[1] or descricao_antecipada}"
                )
                descricao_antecipada = ""
                continue
            if (
                not primeira
                and celulas[1]
                and serializadas
                and serializadas[-1].startswith("PASSO ")
            ):
                serializadas[-1] = f"{serializadas[-1]} {celulas[1]}".strip()
                continue
            if _ATIVIDADE_TABELA_RE.match(primeira) and any(celulas[1:]):
                executante = celulas[1] if len(celulas) > 1 else ""
                marcador = (
                    f" [[EXECUTANTE_TABELA:{executante}]]"
                    if incluir_executante and executante
                    else ""
                )
                serializadas.append(f"{primeira}{marcador}")
                continue
            if normalizada.startswith("COMO FAZER"):
                partes = re.split(
                    r"(?=PORQUE\s+FAZER\s*:)",
                    primeira,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )
                serializadas.extend(
                    parte.strip() for parte in partes if parte.strip()
                )
                continue
        serializadas.append(
            "• " + " | ".join(celula for celula in celulas if celula)
        )
    return ("\n\n" if operacional else "\n").join(serializadas)


def _extrair_pagina_com_tabelas(
    page: fitz.Page,
    tabelas: list[object],
    imagens: list[tuple[float, str]] | None = None,
    eventos_tabela: list[tuple[float, str]] | None = None,
) -> str:
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
            dentro = any(
                _linha_dentro_de_tabela(bbox, tabela_bbox)
                for tabela_bbox in bboxes_tabelas
            )
            texto_linha = "".join(
                span.get("text", "") for span in linha.get("spans", [])
            ).strip()
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

    if eventos_tabela is None:
        eventos.extend(
            (
                tabela.bbox[1],
                _serializar_tabela(tabela, incluir_executante=True),
            )
            for tabela in tabelas
        )
    else:
        eventos.extend(eventos_tabela)
    eventos.extend(imagens or [])
    return "\n\n".join(
        texto
        for _, texto in sorted(eventos, key=lambda evento: evento[0])
        if texto.strip()
    )


def _imagem_pdf_relevante(info: dict, frequencias: Counter[int]) -> bool:
    bbox = tuple(info.get("bbox") or ())
    xref = int(info.get("xref") or 0)
    if (
        len(bbox) != 4
        or xref <= 0
        or frequencias[xref] >= _REPEATED_IMAGE_THRESHOLD
    ):
        return False
    largura = bbox[2] - bbox[0]
    altura = bbox[3] - bbox[1]
    return (
        bbox[1] >= _MIN_IMAGE_TOP
        and largura >= _MIN_IMAGE_WIDTH
        and altura >= _MIN_IMAGE_HEIGHT
        and largura * altura >= _MIN_IMAGE_AREA
    )


def extrair_texto_e_imagens_pdf(
    pdf_bytes: bytes,
    modo_tabelas: str = "imagem",
) -> tuple[str, list[dict]]:
    """Extrai texto e figuras relevantes na mesma ordem visual do PDF."""
    if modo_tabelas not in {"imagem", "texto"}:
        raise ValueError("Modo de extração de tabelas inválido.")
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            infos_por_pagina = [
                page.get_image_info(xrefs=True) for page in document
            ]
            frequencias = Counter(
                int(info.get("xref") or 0)
                for infos in infos_por_pagina
                for info in infos
                if int(info.get("xref") or 0) > 0
            )
            paginas: list[str] = []
            imagens_extraidas: list[dict] = []
            for numero_pagina, page in enumerate(document, start=1):
                eventos_imagem: list[tuple[float, str]] = []
                bboxes_imagem: list[tuple[float, ...]] = []
                for info in infos_por_pagina[numero_pagina - 1]:
                    if not _imagem_pdf_relevante(info, frequencias):
                        continue
                    try:
                        extraida = document.extract_image(int(info["xref"]))
                    except (RuntimeError, ValueError):
                        continue
                    conteudo = extraida.get("image")
                    if not conteudo:
                        continue
                    indice = len(imagens_extraidas) + 1
                    bbox = tuple(info["bbox"])
                    formato = str(extraida.get("ext") or "png").lower()
                    if formato == "jpg":
                        formato = "jpeg"
                    if formato not in {"png", "jpeg"}:
                        try:
                            pixmap = fitz.Pixmap(document, int(info["xref"]))
                            if pixmap.n > 4:
                                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                            conteudo = pixmap.tobytes("png")
                            formato = "png"
                        except (RuntimeError, ValueError):
                            continue
                    imagens_extraidas.append(
                        {
                            "indice": indice,
                            "pagina": numero_pagina,
                            "formato": formato,
                            "largura": int(info.get("width") or 0),
                            "altura": int(info.get("height") or 0),
                            "conteudoBase64": base64.b64encode(
                                conteudo
                            ).decode("ascii"),
                        }
                    )
                    eventos_imagem.append(
                        (bbox[1], f"[[IMAGEM_PDF:{indice}]]")
                    )
                    bboxes_imagem.append(bbox)

                if not eventos_imagem and not page.get_text().strip():
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(
                            _IMAGE_ONLY_PAGE_SCALE, _IMAGE_ONLY_PAGE_SCALE
                        ),
                        alpha=False,
                    )
                    conteudo = pixmap.tobytes("png")
                    indice = len(imagens_extraidas) + 1
                    imagens_extraidas.append(
                        {
                            "indice": indice,
                            "pagina": numero_pagina,
                            "formato": "png",
                            "largura": pixmap.width,
                            "altura": pixmap.height,
                            "conteudoBase64": base64.b64encode(
                                conteudo
                            ).decode("ascii"),
                        }
                    )
                    eventos_imagem.append((0, f"[[IMAGEM_PDF:{indice}]]"))
                    bboxes_imagem.append(tuple(page.rect))

                tabelas_relevantes = [
                    tabela
                    for tabela in page.find_tables().tables
                    if tabela.bbox[3] - tabela.bbox[1] >= 40
                    and not any(
                        _bboxes_se_sobrepoem(tabela.bbox, bbox)
                        for bbox in bboxes_imagem
                    )
                ]
                if tabelas_relevantes:
                    eventos_tabela: list[tuple[float, str]] = []
                    for tabela in tabelas_relevantes:
                        if modo_tabelas == "texto":
                            eventos_tabela.append(
                                (
                                    tabela.bbox[1],
                                    _serializar_tabela(
                                        tabela, incluir_executante=True
                                    ),
                                )
                            )
                            continue
                        recorte = _recortar_tabela_como_png(page, tabela)
                        if recorte is None:
                            eventos_tabela.append(
                                (
                                    tabela.bbox[1],
                                    _serializar_tabela(
                                        tabela, incluir_executante=True
                                    ),
                                )
                            )
                            continue
                        conteudo, largura, altura = recorte
                        texto_alternativo = _TABLE_EXECUTOR_MARKER_RE.sub(
                            " ",
                            _serializar_tabela(tabela),
                        ).strip()
                        indice = len(imagens_extraidas) + 1
                        imagens_extraidas.append(
                            {
                                "indice": indice,
                                "pagina": numero_pagina,
                                "formato": "png",
                                "largura": largura,
                                "altura": altura,
                                "conteudoBase64": base64.b64encode(
                                    conteudo
                                ).decode("ascii"),
                                "textoAlternativo": texto_alternativo,
                            }
                        )
                        eventos_imagem.append(
                            (tabela.bbox[1], f"[[IMAGEM_PDF:{indice}]]")
                        )
                        linhas_tabela = [
                            list(linha) for linha in tabela.extract()
                        ]
                        if _linhas_formam_tabela_operacional(linhas_tabela):
                            texto_operacional = (
                                _serializar_tabela_operacional_para_parser(
                                    tabela
                                )
                            )
                            if texto_operacional:
                                eventos_tabela.append(
                                    (tabela.bbox[1], texto_operacional)
                                )
                    paginas.append(
                        _extrair_pagina_com_tabelas(
                            page,
                            tabelas_relevantes,
                            eventos_imagem,
                            eventos_tabela,
                        )
                    )
                    continue
                eventos = [
                    (float(bloco[1]), bloco[4].strip())
                    for bloco in page.get_text("blocks", sort=True)
                    if bloco[6] == 0 and bloco[4].strip()
                ]
                eventos.extend(eventos_imagem)
                paginas.append(
                    "\n\n".join(
                        texto
                        for _, texto in sorted(
                            eventos, key=lambda evento: evento[0]
                        )
                    )
                )
            return "\n\n".join(paginas), imagens_extraidas
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise ValueError("Não foi possível extrair texto do PDF.") from exc
