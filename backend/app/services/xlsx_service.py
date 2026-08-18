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
)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

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
    texto = escape(valor, {"\"": "&quot;", "'": "&apos;"})
    return f'<c r="{referencia}" t="inlineStr" s="{estilo}"><is><t xml:space="preserve">{texto}</t></is></c>'


def gerar_xlsx_matriz(linhas: list[dict[str, Any]]) -> bytes:
    dados = [XLSX_COLUMNS]
    proximo_id = 1
    for linha in linhas:
        padrao_anexo = linha.get("tipoTarefa") == "Padrão/Anexo"
        identificador = "" if padrao_anexo else str(proximo_id)
        if not padrao_anexo:
            proximo_id += 1
        dados.append(
            [
                _campo_planilha(linha.get("subtarefaHTA")),
                _campo_planilha(linha.get("itemPadrao")),
                _campo_planilha(linha.get("descricao")),
                _campo_planilha(linha.get("tipoTarefa")),
                identificador,
                _campo_planilha(linha.get("descricaoTarefa")),
            ]
        )

    linhas_xml = []
    for indice_linha, valores in enumerate(dados, start=1):
        estilo = 2 if indice_linha == 1 else 1
        celulas = "".join(
            _celula(indice_linha, indice_coluna, valor, estilo)
            for indice_coluna, valor in enumerate(valores, start=1)
        )
        linhas_xml.append(f'<row r="{indice_linha}">{celulas}</row>')
    ultima_linha = max(1, len(dados))
    ultima_coluna = _coluna_excel(len(XLSX_COLUMNS))
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:{ultima_coluna}{ultima_linha}"/><sheetViews><sheetView workbookViewId="0"/></sheetViews>
<sheetFormatPr defaultRowHeight="18"/><cols><col min="1" max="1" width="16" customWidth="1"/><col min="2" max="2" width="24" customWidth="1"/><col min="3" max="3" width="60" customWidth="1"/><col min="4" max="4" width="20" customWidth="1"/><col min="5" max="5" width="16" customWidth="1"/><col min="6" max="6" width="60" customWidth="1"/></cols>
<sheetData>{"".join(linhas_xml)}</sheetData><autoFilter ref="A1:{ultima_coluna}{ultima_linha}"/>
</worksheet>'''

    arquivo = io.BytesIO()
    with zipfile.ZipFile(arquivo, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("[Content_Types].xml", _CONTENT_TYPES)
        pacote.writestr("_rels/.rels", _PACKAGE_RELS)
        pacote.writestr("xl/workbook.xml", _WORKBOOK)
        pacote.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        pacote.writestr("xl/styles.xml", _STYLES)
        pacote.writestr("xl/worksheets/sheet1.xml", sheet)
    return arquivo.getvalue()
