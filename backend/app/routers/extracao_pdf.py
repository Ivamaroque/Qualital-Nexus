import io
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile

from app.core.config import get_settings
from app.services.csv_service import gerar_csv_matriz
from app.services.llm_service import LLMConversionError, converter_blocos_com_gpt
from app.services.normalizer_service import normalizar_linhas
from app.services.parser_rules_service import buscar_parser_rules, filtrar_regras_por_bloco
from app.services.pdf_service import extrair_texto_pdf, limpar_texto_pdf, separar_blocos
from app.services.rag_service import buscar_exemplos_rag

router = APIRouter(prefix="/api/extracao-pdf", tags=["Extração PDF"])
logger = logging.getLogger(__name__)


def _agrupar_blocos(blocos: list[dict[str, Any]], maximo_caracteres: int) -> list[list[dict[str, Any]]]:
    lotes: list[list[dict[str, Any]]] = []
    lote_atual: list[dict[str, Any]] = []
    caracteres_lote = 0

    for bloco in blocos:
        caracteres_bloco = len(bloco["texto"])
        if lote_atual and caracteres_lote + caracteres_bloco > maximo_caracteres:
            lotes.append(lote_atual)
            lote_atual = []
            caracteres_lote = 0
        lote_atual.append(bloco)
        caracteres_lote += caracteres_bloco

    if lote_atual:
        lotes.append(lote_atual)

    return lotes


def _regras_do_lote(regras: list[dict[str, Any]], blocos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regras_selecionadas: list[dict[str, Any]] = []
    identificadores: set[str] = set()

    for bloco in blocos:
        for regra in filtrar_regras_por_bloco(regras, bloco["escopo"], bloco["categoria"]):
            identificador = str(regra.get("id") or regra.get("nome") or id(regra))
            if identificador not in identificadores:
                identificadores.add(identificador)
                regras_selecionadas.append(regra)

    return regras_selecionadas


async def _arquivos_da_requisicao(request: Request) -> list[UploadFile]:
    form = await request.form()
    # ``multi_items`` preserva a sequência original das partes multipart, inclusive
    # quando clientes antigos usam ``files`` e novos usam ``files[]``.
    arquivos = [
        valor
        for chave, valor in form.multi_items()
        if chave in {"files", "files[]"} and isinstance(valor, UploadFile)
    ]
    settings = get_settings()
    if not arquivos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envie ao menos um arquivo PDF.")
    if len(arquivos) > settings.max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O limite é de {settings.max_files} arquivos por envio.",
        )
    return arquivos


async def _processar_arquivos(arquivos: list[UploadFile], incluir_debug: bool) -> tuple[list[dict[str, str]], dict[str, Any]]:
    settings = get_settings()
    regras = await run_in_threadpool(buscar_parser_rules)
    acumuladas: list[dict[str, str]] = []
    debug: dict[str, Any] = {
        "arquivos_processados": [],
        "total_blocos": 0,
        "blocos_detectados": [],
        "categorias": [],
        "exemplos_rag_por_bloco": [],
        "regras_usadas_por_bloco": [],
        "preview_linhas_geradas": [],
    }

    for file_order, arquivo in enumerate(arquivos, start=1):
        filename = arquivo.filename or f"arquivo_{file_order}.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{filename} não é um PDF válido.")
        conteudo = await arquivo.read()
        if not conteudo or not conteudo.startswith(b"%PDF-"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{filename} não é um PDF válido.")
        if len(conteudo) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{filename} excede o limite de {settings.max_file_size_mb} MB.",
            )
        try:
            texto = await run_in_threadpool(extrair_texto_pdf, conteudo)
            texto_limpo = await run_in_threadpool(limpar_texto_pdf, texto)
            blocos = await run_in_threadpool(separar_blocos, texto_limpo)
            if not blocos:
                raise ValueError("Nenhum bloco técnico foi identificado.")
        except ValueError as exc:
            logger.info("Falha ao processar PDF filename=%s etapa=texto", filename)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Não foi possível processar {filename}: {exc}") from exc

        debug["arquivos_processados"].append({"ordem": file_order, "nome": filename, "blocos": len(blocos)})
        for lote in _agrupar_blocos(blocos, settings.extraction_batch_max_chars):
            bloco = lote[0]
            regras_bloco = _regras_do_lote(regras, lote)
            texto_lote = "\n".join(item["texto"] for item in lote)
            palavras_chave = sorted({palavra for item in lote for palavra in item["palavras_chave"]})
            exemplos = await run_in_threadpool(
                buscar_exemplos_rag,
                texto_lote,
                bloco["categoria"],
                palavras_chave,
                settings.rag_examples_limit,
            )
            contexto = {
                "filename": filename,
                "file_order": file_order,
            }
            try:
                linhas = await run_in_threadpool(converter_blocos_com_gpt, lote, regras_bloco, exemplos, contexto)
            except LLMConversionError as exc:
                logger.exception("Falha LLM filename=%s categoria=%s", filename, bloco["categoria"])
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Falha ao converter o bloco técnico de {filename}.",
                ) from exc
            linhas = normalizar_linhas(linhas)
            acumuladas.extend(linhas)
            debug["total_blocos"] += len(lote)
            if incluir_debug:
                for bloco_do_lote in lote:
                    identificador = {"arquivo": filename, "file_order": file_order, "block_order": bloco_do_lote["ordem"]}
                    debug["blocos_detectados"].append({**identificador, **bloco_do_lote})
                    debug["categorias"].append(
                        {**identificador, "categoria": bloco_do_lote["categoria"], "escopo": bloco_do_lote["escopo"]}
                    )
                    debug["exemplos_rag_por_bloco"].append({**identificador, "quantidade": len(exemplos)})
                    debug["regras_usadas_por_bloco"].append({**identificador, "regras": regras_bloco})
                debug["preview_linhas_geradas"].extend(linhas)
        logger.info("Arquivo processado filename=%s blocos=%d", filename, len(blocos))

    return normalizar_linhas(acumuladas), debug


@router.post("/process")
async def processar_extracao_pdf(request: Request) -> StreamingResponse:
    arquivos = await _arquivos_da_requisicao(request)
    try:
        linhas, _ = await _processar_arquivos(arquivos, incluir_debug=False)
        csv = gerar_csv_matriz(linhas)
        return StreamingResponse(
            io.BytesIO(csv.encode("utf-8")),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="matriz_priorizacao.csv"'},
        )
    finally:
        for arquivo in arquivos:
            await arquivo.close()


@router.post("/debug")
async def depurar_extracao_pdf(request: Request) -> dict[str, Any]:
    arquivos = await _arquivos_da_requisicao(request)
    try:
        _, debug = await _processar_arquivos(arquivos, incluir_debug=True)
        return debug
    finally:
        for arquivo in arquivos:
            await arquivo.close()
