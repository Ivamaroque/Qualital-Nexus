import io
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile

from app.core.config import get_settings
from app.services.csv_service import gerar_csv_matriz
from app.services.document_service import extrair_texto_documento
from app.services.llm_service import LLMConversionError, converter_blocos_com_ia
from app.services.matrix_structure_service import consolidar_hierarquia_tarefas
from app.services.normalizer_service import normalizar_linhas
from app.services.parser_rules_service import buscar_parser_rules, filtrar_regras_por_bloco, preparar_blocos_para_ia
from app.services.pdf_service import limpar_texto_pdf, separar_blocos
from app.services.processing_status import (
    atualizar_processamento,
    concluir_processamento,
    falhar_processamento,
    iniciar_processamento,
    obter_processamento,
)

router = APIRouter(prefix="/api/extracao-pdf", tags=["Extração PDF"])
logger = logging.getLogger(__name__)
_PROCESSING_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,100}")
_MAXIMO_BLOCOS_POR_LOTE = 8
_MAXIMO_CARACTERES_POR_LOTE = 12_000
_MENSAGENS_PROGRESSO_OLLAMA = {
    "conectando": "Conectando ao Ollama para gerar a saída estruturada.",
    "aguardando_resposta": "Ollama recebeu o lote e aguarda o início da resposta.",
    "raciocinando": "Ollama está processando o lote antes de emitir a resposta estruturada.",
    "gerando_resposta": "Ollama está transmitindo a resposta estruturada.",
    "resposta_completa": "Ollama concluiu a transmissão; validando a resposta estruturada.",
    "corrigindo_formato": "Ollama retornou um formato inválido; solicitando correção da resposta.",
    "corrigindo_cobertura": "Ollama omitiu blocos; solicitando a recuperação somente dos blocos sem saída.",
}


def _mensagem_progresso_ollama(estado: str) -> str:
    return _MENSAGENS_PROGRESSO_OLLAMA.get(estado, "Ollama está atualizando o processamento do lote.")


def _identificador_processamento(request: Request) -> str | None:
    identificador = request.headers.get("X-Processing-Id", "").strip()
    return identificador if _PROCESSING_ID_PATTERN.fullmatch(identificador) else None


def _agrupar_blocos(
    blocos: list[dict[str, Any]], maximo_caracteres: int, maximo_blocos: int = _MAXIMO_BLOCOS_POR_LOTE
) -> list[list[dict[str, Any]]]:
    lotes: list[list[dict[str, Any]]] = []
    lote_atual: list[dict[str, Any]] = []
    caracteres_lote = 0

    for bloco in blocos:
        caracteres_bloco = len(bloco["texto"])
        if lote_atual and (
            caracteres_lote + caracteres_bloco > maximo_caracteres or len(lote_atual) >= maximo_blocos
        ):
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


def _exemplos_parser_do_lote(regras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    campos = (
        "nome",
        "descricao",
        "escopo",
        "categoria",
        "tipo_tarefa",
        "exemplo_entrada",
        "exemplo_saida_json",
    )
    exemplos: list[dict[str, Any]] = []

    for regra in regras:
        if not regra.get("exemplo_entrada") and not regra.get("exemplo_saida_json"):
            continue
        exemplos.append({campo: regra.get(campo) for campo in campos})

    return exemplos


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envie ao menos um documento PDF ou Word.")
    if len(arquivos) > settings.max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O limite é de {settings.max_files} arquivos por envio.",
        )
    return arquivos


async def _processar_arquivos(
    arquivos: list[UploadFile], incluir_debug: bool, identificador_processamento: str | None = None
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    settings = get_settings()
    acumuladas: list[dict[str, str]] = []
    debug: dict[str, Any] = {
        "arquivos_processados": [],
        "total_blocos": 0,
        "blocos_detectados": [],
        "categorias": [],
        "exemplos_parser_por_bloco": [],
        "regras_usadas_por_bloco": [],
        "preview_linhas_geradas": [],
        "falhas_lotes": [],
    }
    arquivos_preparados: list[dict[str, Any]] = []

    for file_order, arquivo in enumerate(arquivos, start=1):
        filename = arquivo.filename or f"arquivo_{file_order}.pdf"
        if identificador_processamento:
            atualizar_processamento(
                identificador_processamento,
                "preparacao",
                f"Analisando o arquivo {file_order} de {len(arquivos)} para calcular o total real: {filename}",
                arquivo_atual=file_order,
                total_arquivos=len(arquivos),
            )
        conteudo = await arquivo.read()
        if len(conteudo) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{filename} excede o limite de {settings.max_file_size_mb} MB.",
            )
        try:
            texto = await run_in_threadpool(extrair_texto_documento, conteudo, filename)
            texto_limpo = await run_in_threadpool(limpar_texto_pdf, texto)
            blocos = await run_in_threadpool(separar_blocos, texto_limpo)
            if not blocos:
                raise ValueError("Nenhum bloco técnico foi identificado.")
        except ValueError as exc:
            logger.info("Falha ao processar documento filename=%s etapa=texto", filename)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Não foi possível processar {filename}: {exc}") from exc

        debug["arquivos_processados"].append({"ordem": file_order, "nome": filename, "blocos": len(blocos)})
        arquivos_preparados.append({"filename": filename, "file_order": file_order, "blocos": blocos})

    regras = await run_in_threadpool(buscar_parser_rules)
    for arquivo_preparado in arquivos_preparados:
        blocos_preparados = await run_in_threadpool(preparar_blocos_para_ia, arquivo_preparado["blocos"], regras)
        arquivo_preparado["blocos"] = blocos_preparados
        arquivo_preparado["lotes"] = _agrupar_blocos(
            blocos_preparados,
            min(settings.extraction_batch_max_chars, _MAXIMO_CARACTERES_POR_LOTE),
        )

    total_lotes = sum(len(arquivo_preparado["lotes"]) for arquivo_preparado in arquivos_preparados)
    etapas_totais = len(arquivos) + 1 + (total_lotes * 2) + 1
    etapas_concluidas = len(arquivos) + 1
    debug["etapas_totais"] = etapas_totais
    debug["etapas_concluidas"] = etapas_concluidas
    if identificador_processamento:
        atualizar_processamento(
            identificador_processamento,
            "regras",
            f"Total real calculado: {etapas_totais} etapas técnicas. Aplicando regras e exemplos do parser.",
            arquivo_atual=len(arquivos),
            total_arquivos=len(arquivos),
            etapas_concluidas=etapas_concluidas,
            etapas_totais=etapas_totais,
        )

    for arquivo_preparado in arquivos_preparados:
        filename = arquivo_preparado["filename"]
        file_order = arquivo_preparado["file_order"]
        blocos = arquivo_preparado["blocos"]
        lotes = arquivo_preparado["lotes"]
        linhas_arquivo: list[dict[str, Any]] = []
        for lote_order, lote in enumerate(lotes, start=1):
            regras_bloco = _regras_do_lote(regras, lote)
            exemplos_parser = _exemplos_parser_do_lote(regras_bloco)
            contexto = {
                "filename": filename,
                "file_order": file_order,
            }

            def atualizar_progresso_ollama(estado: str, trechos: int, caracteres: int) -> None:
                if not identificador_processamento:
                    return

                atualizar_processamento(
                    identificador_processamento,
                    "ia",
                    _mensagem_progresso_ollama(estado),
                    arquivo_atual=file_order,
                    total_arquivos=len(arquivos),
                    lote_atual=lote_order,
                    total_lotes=len(lotes),
                    etapas_concluidas=etapas_concluidas,
                    etapas_totais=etapas_totais,
                    ia_status=estado,
                    ia_trechos_recebidos=trechos,
                    ia_caracteres_recebidos=caracteres,
                )

            try:
                if identificador_processamento:
                    atualizar_processamento(
                        identificador_processamento,
                        "ia",
                        f"A IA está gerando linhas para o lote {lote_order} de {len(lotes)} em {filename}.",
                        arquivo_atual=file_order,
                        total_arquivos=len(arquivos),
                        lote_atual=lote_order,
                        total_lotes=len(lotes),
                        etapas_concluidas=etapas_concluidas,
                        etapas_totais=etapas_totais,
                        ia_status="enviando_lote",
                        ia_trechos_recebidos=0,
                        ia_caracteres_recebidos=0,
                    )
                linhas = await run_in_threadpool(
                    converter_blocos_com_ia,
                    lote,
                    regras_bloco,
                    exemplos_parser,
                    contexto,
                    atualizar_progresso_ollama if identificador_processamento else None,
                )
            except LLMConversionError as exc:
                logger.exception(
                    "Falha LLM filename=%s lote=%s ordens_blocos=%s",
                    filename,
                    lote_order,
                    [bloco_do_lote["ordem"] for bloco_do_lote in lote],
                )
                debug["falhas_lotes"].append(
                    {
                        "arquivo": filename,
                        "file_order": file_order,
                        "lote_order": lote_order,
                        "ordens_blocos": [bloco_do_lote["ordem"] for bloco_do_lote in lote],
                        "erro": str(exc),
                    }
                )
                etapas_concluidas += 2
                if identificador_processamento:
                    atualizar_processamento(
                        identificador_processamento,
                        "parcial",
                        f"O lote {lote_order} falhou; continuando a extração para gerar um CSV parcial.",
                        arquivo_atual=file_order,
                        total_arquivos=len(arquivos),
                        lote_atual=lote_order,
                        total_lotes=len(lotes),
                        etapas_concluidas=etapas_concluidas,
                        etapas_totais=etapas_totais,
                    )
                continue
            etapas_concluidas += 1
            if identificador_processamento:
                atualizar_processamento(
                    identificador_processamento,
                    "normalizacao",
                    f"Consolidando as linhas do lote {lote_order} de {len(lotes)} em {filename}.",
                    arquivo_atual=file_order,
                    total_arquivos=len(arquivos),
                    lote_atual=lote_order,
                    total_lotes=len(lotes),
                    etapas_concluidas=etapas_concluidas,
                    etapas_totais=etapas_totais,
                )
            etapas_concluidas += 1
            linhas_arquivo.extend(linhas)
            debug["total_blocos"] += len(lote)
            if incluir_debug:
                for bloco_do_lote in lote:
                    identificador = {"arquivo": filename, "file_order": file_order, "block_order": bloco_do_lote["ordem"]}
                    debug["blocos_detectados"].append({**identificador, **bloco_do_lote})
                    debug["categorias"].append(
                        {**identificador, "categoria": bloco_do_lote["categoria"], "escopo": bloco_do_lote["escopo"]}
                    )
                    debug["exemplos_parser_por_bloco"].append({**identificador, "quantidade": len(exemplos_parser)})
                    debug["regras_usadas_por_bloco"].append({**identificador, "regras": regras_bloco})
        linhas_arquivo = await run_in_threadpool(consolidar_hierarquia_tarefas, blocos, linhas_arquivo)
        linhas_normalizadas_arquivo = normalizar_linhas(linhas_arquivo)
        acumuladas.extend(linhas_normalizadas_arquivo)
        if incluir_debug:
            debug["preview_linhas_geradas"].extend(linhas_normalizadas_arquivo)
        logger.info("Arquivo processado filename=%s blocos=%d", filename, len(blocos))

    debug["etapas_concluidas"] = etapas_concluidas
    return acumuladas, debug


@router.get("/process/{identificador}/status")
async def status_processamento(identificador: str) -> dict[str, Any]:
    if not _PROCESSING_ID_PATTERN.fullmatch(identificador):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processamento não encontrado.")
    processamento = obter_processamento(identificador)
    if processamento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processamento não encontrado ou expirado.")
    return processamento


@router.post("/process")
async def processar_extracao_pdf(request: Request) -> StreamingResponse:
    identificador = _identificador_processamento(request)
    if identificador:
        iniciar_processamento(identificador)
    arquivos: list[UploadFile] = []
    try:
        arquivos = await _arquivos_da_requisicao(request)
        linhas, debug = await _processar_arquivos(arquivos, incluir_debug=False, identificador_processamento=identificador)
        if identificador:
            atualizar_processamento(
                identificador,
                "csv",
                "Gerando o arquivo CSV.",
                etapas_concluidas=debug["etapas_concluidas"],
                etapas_totais=debug["etapas_totais"],
            )
        csv = gerar_csv_matriz(linhas)
        falhas_lotes = debug["falhas_lotes"]
        arquivo_csv = "matriz_priorizacao_parcial.csv" if falhas_lotes else "matriz_priorizacao.csv"
        if identificador:
            mensagem = (
                f"CSV parcial gerado com {len(falhas_lotes)} lote(s) sem saída da IA."
                if falhas_lotes
                else "CSV gerado e pronto para download."
            )
            concluir_processamento(identificador, mensagem, falhas_lotes=falhas_lotes)
        return StreamingResponse(
            io.BytesIO(csv.encode("utf-8")),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{arquivo_csv}"',
                "X-Extraction-Partial": str(bool(falhas_lotes)).lower(),
                "X-Extraction-Failures": str(len(falhas_lotes)),
            },
        )
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
async def depurar_extracao_pdf(request: Request) -> dict[str, Any]:
    arquivos = await _arquivos_da_requisicao(request)
    try:
        _, debug = await _processar_arquivos(arquivos, incluir_debug=True)
        return debug
    finally:
        for arquivo in arquivos:
            await arquivo.close()
