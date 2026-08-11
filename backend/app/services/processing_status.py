from datetime import UTC, datetime, timedelta
import logging
from threading import RLock
from typing import Any


_STATUS_TTL = timedelta(hours=1)
logger = logging.getLogger(__name__)
_lock = RLock()
_processamentos: dict[str, dict[str, Any]] = {}


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _limpar_expirados() -> None:
    limite = datetime.now(UTC) - _STATUS_TTL
    expirados = [
        identificador
        for identificador, processamento in _processamentos.items()
        if datetime.fromisoformat(processamento["atualizado_em"]) < limite
    ]
    for identificador in expirados:
        del _processamentos[identificador]


def iniciar_processamento(identificador: str, total_arquivos: int = 0) -> None:
    with _lock:
        _limpar_expirados()
        _processamentos[identificador] = {
            "status": "processando",
            "etapa": "envio",
            "mensagem": "Recebendo arquivos para processamento.",
            "arquivo_atual": 0,
            "total_arquivos": total_arquivos,
            "lote_atual": 0,
            "total_lotes": 0,
            "etapas_concluidas": 0,
            "etapas_totais": 0,
            "progresso_percentual": 0,
            "ia_status": "",
            "ia_trechos_recebidos": 0,
            "ia_caracteres_recebidos": 0,
            "atualizado_em": _agora(),
        }
        logger.info("Processamento iniciado id=%s total_arquivos=%d", identificador, total_arquivos)


def atualizar_processamento(identificador: str, etapa: str, mensagem: str, **detalhes: Any) -> None:
    with _lock:
        processamento = _processamentos.get(identificador)
        if processamento is None:
            return
        processamento.update({"etapa": etapa, "mensagem": mensagem, **detalhes, "atualizado_em": _agora()})
        etapas_totais = processamento["etapas_totais"]
        if etapas_totais:
            processamento["progresso_percentual"] = round(
                (processamento["etapas_concluidas"] / etapas_totais) * 100
            )
        logger.info("Processamento id=%s etapa=%s mensagem=%s", identificador, etapa, mensagem)


def concluir_processamento(
    identificador: str,
    mensagem: str = "CSV gerado e pronto para download.",
    **detalhes: Any,
) -> None:
    with _lock:
        processamento = _processamentos.get(identificador)
        if processamento is None:
            return
        processamento.update(
            {
                "status": "concluido",
                "etapa": "concluido",
                "mensagem": mensagem,
                "etapas_concluidas": processamento["etapas_totais"],
                "progresso_percentual": 100,
                **detalhes,
                "atualizado_em": _agora(),
            }
        )
        logger.info("Processamento concluído id=%s", identificador)


def falhar_processamento(identificador: str, mensagem: str) -> None:
    with _lock:
        processamento = _processamentos.get(identificador)
        if processamento is None:
            return
        processamento.update(
            {
                "status": "erro",
                "etapa": "erro",
                "mensagem": mensagem,
                "atualizado_em": _agora(),
            }
        )
        logger.error("Processamento falhou id=%s mensagem=%s", identificador, mensagem)


def obter_processamento(identificador: str) -> dict[str, Any] | None:
    with _lock:
        _limpar_expirados()
        processamento = _processamentos.get(identificador)
        return dict(processamento) if processamento else None
