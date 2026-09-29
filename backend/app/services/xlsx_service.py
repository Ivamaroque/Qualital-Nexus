import base64
import io
import zipfile
from typing import Any
from xml.sax.saxutils import escape

XLSX_COLUMNS = (
    "Subtarefa (HTA)",
    "Item (Padrão)",
    "Descrição da tarefa (Padrão)",
    "Tipo da tarefa",
    "ID da Subtarefa",
    "Descrição da tarefa (HTA)",
    "Executante",
)

_PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Matriz" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><sz val="11"/><name val="Aptos"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="D9EAF7"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf><xf numFmtId="0" fontId="1" fillId="1" borderId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf></cellXfs>
</styleSheet>"""


def _campo_planilha(valor: Any) -> str:
    return "\n".join(
        " ".join(linha.split())
        for linha in str(valor or "").splitlines()
        if linha.strip()
    )


def _coluna_excel(indice: int) -> str:
    resultado = ""
    while indice:
        indice, resto = divmod(indice - 1, 26)
        resultado = chr(65 + resto) + resultado
    return resultado


def _celula(linha: int, coluna: int, valor: str, estilo: int) -> str:
    referencia = f"{_coluna_excel(coluna)}{linha}"
    texto = escape(valor, {'"': "&quot;", "'": "&apos;"})
    return f'<c r="{referencia}" t="inlineStr" s="{estilo}"><is><t xml:space="preserve">{texto}</t></is></c>'


def _dimensoes_exibicao(largura: int, altura: int) -> tuple[int, int]:
    largura = max(1, largura)
    altura = max(1, altura)
    escala = min(1.0, 420 / largura, 280 / altura)
    return max(1, round(largura * escala)), max(1, round(altura * escala))


def _content_types(formatos: set[str], com_desenho: bool) -> str:
    defaults = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    if "png" in formatos:
        defaults.append('<Default Extension="png" ContentType="image/png"/>')
    if "jpeg" in formatos:
        defaults.append('<Default Extension="jpeg" ContentType="image/jpeg"/>')
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    if com_desenho:
        overrides.append('<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + "".join(defaults + overrides)
        + "</Types>"
    )


def gerar_xlsx_matriz(linhas: list[dict[str, Any]]) -> bytes:
    dados = [XLSX_COLUMNS]
    imagens: list[dict[str, Any]] = []
    proximo_id = 1
    for indice_saida, linha in enumerate(linhas, start=2):
        tem_imagem = bool(linha.get("imagemBase64"))
        padrao_anexo = linha.get("tipoTarefa") == "Padrão/Anexo"
        identificador = "" if padrao_anexo or tem_imagem else str(proximo_id)
        if not padrao_anexo and not tem_imagem:
            proximo_id += 1
        dados.append(
            ["", "", "", "", "", "", ""]
            if tem_imagem
            else [
                _campo_planilha(linha.get("subtarefaHTA")),
                _campo_planilha(linha.get("itemPadrao")),
                _campo_planilha(linha.get("descricao")),
                _campo_planilha(linha.get("tipoTarefa")),
                identificador,
                _campo_planilha(linha.get("descricaoTarefa")),
                _campo_planilha(linha.get("executante")),
            ]
        )
        if tem_imagem:
            formato = str(linha.get("imagemFormato") or "png").lower().replace("jpg", "jpeg")
            if formato not in {"png", "jpeg"}:
                continue
            try:
                conteudo = base64.b64decode(str(linha["imagemBase64"]), validate=True)
            except (ValueError, TypeError):
                continue
            if not conteudo:
                continue
            largura, altura = _dimensoes_exibicao(
                int(linha.get("imagemLargura") or 0),
                int(linha.get("imagemAltura") or 0),
            )
            imagens.append(
                {
                    "linha": indice_saida,
                    "formato": formato,
                    "conteudo": conteudo,
                    "largura": largura,
                    "altura": altura,
                    "descricao": (
                        _campo_planilha(linha.get("descricao"))[:1000]
                        or "Imagem extraída do documento de origem"
                    ),
                }
            )

    imagens_por_linha = {imagem["linha"]: imagem for imagem in imagens}
    linhas_xml = []
    for indice_linha, valores in enumerate(dados, start=1):
        estilo = 2 if indice_linha == 1 else 1
        celulas = "".join(
            _celula(indice_linha, indice_coluna, valor, estilo)
            for indice_coluna, valor in enumerate(valores, start=1)
        )
        imagem = imagens_por_linha.get(indice_linha)
        atributos = (
            f' ht="{imagem["altura"] * 0.75 + 6:.2f}" customHeight="1"'
            if imagem
            else ""
        )
        linhas_xml.append(f'<row r="{indice_linha}"{atributos}>{celulas}</row>')

    ultima_linha = max(1, len(dados))
    ultima_coluna = _coluna_excel(len(XLSX_COLUMNS))
    drawing_tag = '<drawing r:id="rId1"/>' if imagens else ""
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<dimension ref="A1:{ultima_coluna}{ultima_linha}"/><sheetViews><sheetView workbookViewId="0"/></sheetViews>
<sheetFormatPr defaultRowHeight="18"/><cols><col min="1" max="1" width="16" customWidth="1"/><col min="2" max="2" width="24" customWidth="1"/><col min="3" max="3" width="60" customWidth="1"/><col min="4" max="4" width="20" customWidth="1"/><col min="5" max="5" width="16" customWidth="1"/><col min="6" max="6" width="60" customWidth="1"/><col min="7" max="7" width="30" customWidth="1"/></cols>
<sheetData>{"".join(linhas_xml)}</sheetData><autoFilter ref="A1:{ultima_coluna}{ultima_linha}"/>{drawing_tag}
</worksheet>'''

    desenho = ""
    rels_desenho = ""
    if imagens:
        ancoras = []
        relacoes = []
        for indice, imagem in enumerate(imagens, start=1):
            linha_zero = imagem["linha"] - 1
            cx = imagem["largura"] * 9525
            cy = imagem["altura"] * 9525
            ancoras.append(f'''<xdr:oneCellAnchor>
<xdr:from><xdr:col>2</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{linha_zero}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
<xdr:ext cx="{cx}" cy="{cy}"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{indice}" name="Figura {indice}" descr="{escape(imagem["descricao"], {'"': '&quot;', "'": '&apos;'})}"/><xdr:cNvPicPr/></xdr:nvPicPr>
<xdr:blipFill><a:blip r:embed="rId{indice}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/>
</xdr:oneCellAnchor>''')
            relacoes.append(
                f'<Relationship Id="rId{indice}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{indice}.{imagem["formato"]}"/>'
            )
        desenho = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + "".join(ancoras)
            + "</xdr:wsDr>"
        )
        rels_desenho = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(relacoes)
            + "</Relationships>"
        )

    arquivo = io.BytesIO()
    with zipfile.ZipFile(arquivo, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("[Content_Types].xml", _content_types({imagem["formato"] for imagem in imagens}, bool(imagens)))
        pacote.writestr("_rels/.rels", _PACKAGE_RELS)
        pacote.writestr("xl/workbook.xml", _WORKBOOK)
        pacote.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        pacote.writestr("xl/styles.xml", _STYLES)
        pacote.writestr("xl/worksheets/sheet1.xml", sheet)
        if imagens:
            pacote.writestr(
                "xl/worksheets/_rels/sheet1.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>'
                '</Relationships>',
            )
            pacote.writestr("xl/drawings/drawing1.xml", desenho)
            pacote.writestr("xl/drawings/_rels/drawing1.xml.rels", rels_desenho)
            for indice, imagem in enumerate(imagens, start=1):
                pacote.writestr(f'xl/media/image{indice}.{imagem["formato"]}', imagem["conteudo"])
    return arquivo.getvalue()
