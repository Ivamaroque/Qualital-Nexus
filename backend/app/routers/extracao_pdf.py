import io
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile

from app.core.config import get_settings
from app.core.security import require_authenticated_user
from app.services.csv_service import gerar_csv_matriz
from app.services.extraction_pipeline_service import ExtractionValidationError, processar_arquivos
from app.services.processing_status import (
    atualizar_processamento,
    concluir_processamento,
    falhar_processamento,
    iniciar_processamento,
    obter_processamento,
)
from app.services.xlsx_service import gerar_xlsx_matriz

router = APIRouter(
    prefix="/api/extracao-pdf",
    tags=["Extração PDF"],
    dependencies=[Depends(require_authenticated_user)],
)
_PROCESSING_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,100}")


def _identificador_processamento(request: Request) -> str | None:
    identificador = request.headers.get("X-Processing-Id", "").strip()
    return identificador if _PROCESSING_ID_PATTERN.fullmatch(identificador) else None


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envie ao menos um documento PDF, DOC ou DOCX.")
    if len(arquivos) > settings.max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O limite é de {settings.max_files} arquivos por envio.",
        )
    return arquivos


@router.get("/process/{identificador}/status")
async def status_processamento(identificador: str) -> dict[str, Any]:
    if not _PROCESSING_ID_PATTERN.fullmatch(identificador):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processamento não encontrado.")
    processamento = obter_processamento(identificador)
    if processamento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processamento não encontrado ou expirado.")
    return processamento


@router.post("/process")
async def processar_extracao_pdf(
    request: Request,
    formato: Literal["xlsx", "csv"] = Query(default="xlsx", alias="format"),
    modo_tabelas: Literal["imagem", "texto"] = Query(default="imagem", alias="table_mode"),
) -> StreamingResponse:
    identificador = _identificador_processamento(request)
    if identificador:
        iniciar_processamento(identificador)
    arquivos: list[UploadFile] = []
    try:
        arquivos = await _arquivos_da_requisicao(request)
        linhas, debug = await processar_arquivos(
            arquivos,
            incluir_debug=False,
            identificador_processamento=identificador,
            modo_tabelas=modo_tabelas,
        )
        formato_nome = formato.upper()
        if identificador:
            atualizar_processamento(
                identificador,
                formato,
                f"Gerando o arquivo {formato_nome}.",
                etapas_concluidas=debug["etapas_concluidas"],
                etapas_totais=debug["etapas_totais"],
            )
        falhas_lotes = debug["falhas_lotes"]
        extensao = "xlsx" if formato == "xlsx" else "csv"
        nome_base = "matriz_priorizacao_parcial" if falhas_lotes else "matriz_priorizacao"
        arquivo_saida = f"{nome_base}.{extensao}"
        conteudo_saida = gerar_xlsx_matriz(linhas) if formato == "xlsx" else gerar_csv_matriz(linhas).encode("utf-8")
        if identificador:
            mensagem = (
                f"{formato_nome} parcial gerado com {len(falhas_lotes)} lote(s) sem saída da IA."
                if falhas_lotes
                else f"{formato_nome} gerado e pronto para download."
            )
            concluir_processamento(identificador, mensagem, falhas_lotes=falhas_lotes)
        return StreamingResponse(
            io.BytesIO(conteudo_saida),
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if formato == "xlsx"
                else "text/csv; charset=utf-8"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{arquivo_saida}"',
                "X-Extraction-Format": formato,
                "X-Extraction-Partial": str(bool(falhas_lotes)).lower(),
                "X-Extraction-Failures": str(len(falhas_lotes)),
            },
        )
    except ExtractionValidationError as exc:
        if identificador:
            falhar_processamento(identificador, str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException as exc:
        if identificador:
            falhar_processamento(identificador, str(exc.detail))
        raise
    except Exception:
        if identificador:
            falhar_processamento(identificador, "O processamento foi interrompido por um erro interno.")
        raise
    finally:
        for arquivo in arquivos:
            await arquivo.close()


@router.post("/debug")
async def depurar_extracao_pdf(
    request: Request,
    modo_tabelas: Literal["imagem", "texto"] = Query(default="imagem", alias="table_mode"),
) -> dict[str, Any]:
    arquivos = await _arquivos_da_requisicao(request)
    try:
        _, debug = await processar_arquivos(
            arquivos,
            incluir_debug=True,
            modo_tabelas=modo_tabelas,
        )
        return debug
    except ExtractionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        for arquivo in arquivos:
            await arquivo.close()
