import io
import re
import struct
import zipfile
from pathlib import Path

import olefile
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError

from app.services.pdf_service import extrair_texto_pdf


EXTENSOES_DOCUMENTO_ACEITAS = {".pdf", ".doc", ".docx"}
_ASSINATURA_DOC = bytes.fromhex("D0CF11E0A1B11AE1")
_MAXIMO_DESCOMPACTADO_DOCX = 100 * 1024 * 1024


def _extensao_documento(filename: str) -> str:
    return Path(filename).suffix.lower()


def _validar_docx(conteudo: bytes) -> None:
    if not conteudo.startswith(b"PK"):
        raise ValueError("O conteúdo não corresponde a um arquivo DOCX válido.")
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            nomes = set(pacote.namelist())
            tamanho_total = sum(item.file_size for item in pacote.infolist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("O conteúdo não corresponde a um arquivo DOCX válido.") from exc
    if "[Content_Types].xml" not in nomes or "word/document.xml" not in nomes:
        raise ValueError("O conteúdo não corresponde a um arquivo DOCX válido.")
    if tamanho_total > _MAXIMO_DESCOMPACTADO_DOCX:
        raise ValueError("O conteúdo descompactado do DOCX excede o limite de segurança.")


def validar_documento(filename: str, conteudo: bytes) -> str:
    extensao = _extensao_documento(filename)
    if extensao not in EXTENSOES_DOCUMENTO_ACEITAS:
        permitidas = ", ".join(sorted(EXTENSOES_DOCUMENTO_ACEITAS))
        raise ValueError(f"Extensão não permitida. Use {permitidas}.")
    if not conteudo:
        raise ValueError("O arquivo está vazio.")
    if extensao == ".pdf" and not conteudo.startswith(b"%PDF-"):
        raise ValueError("O conteúdo não corresponde a um arquivo PDF válido.")
    if extensao == ".doc" and not conteudo.startswith(_ASSINATURA_DOC):
        raise ValueError("O conteúdo não corresponde a um arquivo DOC válido.")
    if extensao == ".docx":
        _validar_docx(conteudo)
    return extensao


def _limpar_controles_word(texto: str) -> str:
    texto = texto.replace("\x07\x07", "\n")
    texto = texto.replace("\x07", "\t")
    texto = texto.replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    texto = re.sub(r"[\x00-\x08\x0e-\x1f]", "", texto)
    return texto


def _extrair_texto_doc(conteudo: bytes) -> str:
    try:
        with olefile.OleFileIO(io.BytesIO(conteudo)) as arquivo_ole:
            if not arquivo_ole.exists("WordDocument"):
                raise ValueError("O DOC não contém o fluxo WordDocument.")
            word_document = arquivo_ole.openstream("WordDocument").read()
            if len(word_document) < 0x1AA:
                raise ValueError("A estrutura interna do DOC está incompleta.")
            flags = struct.unpack_from("<H", word_document, 0x0A)[0]
            tabela_nome = "1Table" if flags & 0x0200 else "0Table"
            if not arquivo_ole.exists(tabela_nome):
                raise ValueError(f"O DOC não contém o fluxo {tabela_nome}.")
            tabela = arquivo_ole.openstream(tabela_nome).read()
    except (OSError, IOError, olefile.OleFileError) as exc:
        raise ValueError("Não foi possível abrir a estrutura binária do DOC.") from exc

    inicio_clx, tamanho_clx = struct.unpack_from("<II", word_document, 0x1A2)
    fim_clx = inicio_clx + tamanho_clx
    if tamanho_clx < 5 or fim_clx > len(tabela):
        raise ValueError("A tabela de texto do DOC está inválida.")
    clx = tabela[inicio_clx:fim_clx]
    posicao = 0
    while posicao < len(clx) and clx[posicao] == 0x01:
        if posicao + 3 > len(clx):
            raise ValueError("A tabela de propriedades do DOC está truncada.")
        tamanho_propriedades = struct.unpack_from("<H", clx, posicao + 1)[0]
        posicao += 3 + tamanho_propriedades
    if posicao + 5 > len(clx) or clx[posicao] != 0x02:
        raise ValueError("A tabela de segmentos de texto do DOC não foi encontrada.")

    tamanho_segmentos = struct.unpack_from("<I", clx, posicao + 1)[0]
    segmentos = clx[posicao + 5 : posicao + 5 + tamanho_segmentos]
    if len(segmentos) != tamanho_segmentos or tamanho_segmentos < 4 or (tamanho_segmentos - 4) % 12:
        raise ValueError("A tabela de segmentos de texto do DOC está truncada.")
    quantidade = (tamanho_segmentos - 4) // 12
    limites = struct.unpack_from(f"<{quantidade + 1}I", segmentos, 0)
    inicio_descritores = 4 * (quantidade + 1)
    partes: list[str] = []

    for indice in range(quantidade):
        quantidade_caracteres = limites[indice + 1] - limites[indice]
        if quantidade_caracteres < 0:
            raise ValueError("A sequência de segmentos de texto do DOC está inválida.")
        inicio_descritor = inicio_descritores + (indice * 8)
        posicao_codificada = struct.unpack_from("<I", segmentos, inicio_descritor + 2)[0]
        comprimido = bool(posicao_codificada & 0x40000000)
        posicao_texto = posicao_codificada & 0x3FFFFFFF
        if comprimido:
            posicao_texto //= 2
            tamanho_texto = quantidade_caracteres
            codificacao = "cp1252"
        else:
            tamanho_texto = quantidade_caracteres * 2
            codificacao = "utf-16le"
        fim_texto = posicao_texto + tamanho_texto
        if fim_texto > len(word_document):
            raise ValueError("Um segmento de texto do DOC aponta para uma posição inválida.")
        partes.append(word_document[posicao_texto:fim_texto].decode(codificacao, errors="replace"))

    texto = _limpar_controles_word("".join(partes)).strip()
    if not texto:
        raise ValueError("Não foi possível extrair texto do DOC.")
    return texto


def _texto_tabela_docx(tabela: Table) -> str:
    linhas: list[str] = []
    for linha in tabela.rows:
        celulas: list[str] = []
        elementos_processados: set[int] = set()
        for celula in linha.cells:
            identificador = id(celula._tc)
            if identificador in elementos_processados:
                continue
            elementos_processados.add(identificador)
            celulas.append(" ".join(celula.text.split()))
        if any(celulas):
            linhas.append("\t".join(celulas))
    return "\n".join(linhas)


def _extrair_texto_docx(conteudo: bytes) -> str:
    try:
        documento = Document(io.BytesIO(conteudo))
    except (KeyError, OSError, PackageNotFoundError, ValueError, XMLSyntaxError, zipfile.BadZipFile) as exc:
        raise ValueError("Não foi possível abrir o DOCX.") from exc
    partes: list[str] = []
    for elemento in documento.iter_inner_content():
        if isinstance(elemento, Paragraph):
            texto = elemento.text.strip()
        elif isinstance(elemento, Table):
            texto = _texto_tabela_docx(elemento)
        else:
            texto = ""
        if texto:
            partes.append(texto)
    texto = "\n\n".join(partes).strip()
    if not texto:
        raise ValueError("Não foi possível extrair texto do DOCX.")
    return texto


def extrair_texto_documento(conteudo: bytes, filename: str) -> str:
    extensao = validar_documento(filename, conteudo)
    if extensao == ".pdf":
        return extrair_texto_pdf(conteudo)
    if extensao == ".doc":
        return _extrair_texto_doc(conteudo)
    return _extrair_texto_docx(conteudo)
