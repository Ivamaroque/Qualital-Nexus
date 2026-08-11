import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.openai_client import get_openai_client
from app.schemas.matriz import MatrizLinha, MatrizOutput

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Você é um conversor técnico do Qualital Nexus. Sua função é converter blocos de PDFs "
    "técnicos em linhas para a Matriz de Priorização. Siga as regras do parser, os exemplos "
    "do parser e preserve a granularidade do documento. Não invente conteúdo. Não resuma "
    "excessivamente. Não crie linhas para cabeçalho, rodapé, página, INTERNA ou aprovação. "
    "Retorne somente um objeto JSON compatível com o schema solicitado."
)

JSON_OUTPUT_INSTRUCTION = (
    'Responda somente com um objeto JSON, sem markdown ou texto adicional, no formato '
    '{"linhas":[{"ordemBloco":1,"itemPadrao":"","descricao":"","tipoTarefa":"Execução",'
    '"subtarefaHTA":"","descricaoTarefa":""}]}. A chave raiz obrigatória é "linhas". '
    'Cada item de "linhas" deve conter "ordemBloco", "descricao" e "tipoTarefa". Para cada bloco recebido, '
    'retorne ao menos uma linha com a mesma ordemBloco; use tipoTarefa "Ignorar" somente para ruído. '
    'Os únicos valores de saída para tipoTarefa são "Padrão/Anexo", "Título/Subtítulo", "Informação" e "Execução".'
)

JSON_RETRY_INSTRUCTION = (
    'A resposta anterior é inválida porque não contém a chave raiz "linhas". Gere novamente somente o JSON no formato '
    'solicitado. Não repita os blocos de entrada e não use campos como "ordem" ou "texto" na raiz.'
)

COVERAGE_RETRY_INSTRUCTION = (
    "A resposta anterior omitiu blocos. Converta somente os blocos recebidos agora e retorne ao menos uma linha para "
    "cada ordemBloco. Use exatamente o valor global do campo ordem de cada bloco, mesmo quando ele não começar em 1. "
    "Não use a posição local do lote e não crie ordens que não estejam na entrada."
)

_TIPOS_TAREFA_POR_CATEGORIA = {
    "padrao_documento": "Padrão/Anexo",
    "secao_principal": "Título/Subtítulo",
    "titulo_tabela": "Título/Subtítulo",
    "objetivo": "Informação",
    "atividade_tabela_2": "Execução",
    "atividade_anomalia": "Execução",
    "como_fazer": "Execução",
}

OllamaProgressCallback = Callable[[str, int, int], None]


class LLMConversionError(RuntimeError):
    """Erro previsível ao transformar blocos com um provedor de IA."""


def _criar_prompt(
    blocos: list[dict[str, Any]],
    regras_parser: list[dict[str, Any]],
    exemplos_parser: list[dict[str, Any]],
    contexto: dict[str, Any],
) -> dict[str, Any]:
    regras_sem_exemplos = [
        {
            campo: valor
            for campo, valor in regra.items()
            if campo not in {"exemplo_entrada", "exemplo_saida_json"}
        }
        for regra in regras_parser
    ]
    return {
        "contexto_arquivo": contexto.get("filename", ""),
        "file_order": contexto.get("file_order"),
        "instrucao": (
            "Converta todos os blocos na ordem recebida. Cada linha deve informar ordemBloco igual ao campo ordem "
            "do bloco de origem. Um bloco pode gerar várias linhas, mas nenhum bloco pode ficar sem linha. "
            "A orientacao_parser indica a regra que correspondeu ao trecho; siga-a quando existir. Use itemPadraoDetectado "
            "somente na linha de título da seção, removendo a numeração do início da descricao; para linhas de conteúdo "
            "da mesma seção deixe itemPadrao vazio. Para tarefas de execução, preencha subtarefaHTA com a ação curta e "
            "descricaoTarefa com o detalhamento explícito no PDF; nos demais tipos, deixe esses dois campos vazios."
        ),
        "regras_parser": regras_sem_exemplos,
        "exemplos_parser": exemplos_parser,
        "ordensBlocoPermitidas": [bloco["ordem"] for bloco in blocos],
        "blocos": blocos,
    }


def _matriz_de_conteudo_json(conteudo: str) -> MatrizOutput:
    texto = conteudo.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", maxsplit=1)[1].rsplit("```", maxsplit=1)[0].strip()
    try:
        return MatrizOutput.model_validate_json(texto)
    except ValueError as exc:
        raise LLMConversionError(
            'O provedor de IA retornou um JSON fora do formato esperado. A resposta deve conter a chave "linhas".'
        ) from exc


def _validar_cobertura_dos_blocos(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> None:
    ordens_esperadas = {bloco["ordem"] for bloco in blocos}
    ordens_recebidas = {linha.ordemBloco for linha in matriz.linhas}
    ordens_desconhecidas = ordens_recebidas - ordens_esperadas
    ordens_ausentes = ordens_esperadas - ordens_recebidas
    if ordens_desconhecidas or ordens_ausentes:
        detalhes: list[str] = []
        if ordens_ausentes:
            detalhes.append(f"blocos sem saída: {sorted(ordens_ausentes)}")
        if ordens_desconhecidas:
            detalhes.append(f"ordens inexistentes: {sorted(ordens_desconhecidas)}")
        raise LLMConversionError("A IA não cobriu todos os blocos do parser (" + "; ".join(detalhes) + ").")


def _obter_blocos_sem_saida(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> list[dict[str, Any]]:
    ordens_recebidas = {linha.ordemBloco for linha in matriz.linhas}
    return [bloco for bloco in blocos if bloco["ordem"] not in ordens_recebidas]


def _normalizar_ordens_da_resposta(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> MatrizOutput:
    """Converte índices locais que alguns modelos retornam para a ordem global do PDF."""
    ordens_esperadas = [bloco["ordem"] for bloco in blocos]
    conjunto_ordens_esperadas = set(ordens_esperadas)
    resposta_usa_indices_locais = (
        ordens_esperadas != list(range(1, len(blocos) + 1))
        and any(
            linha.ordemBloco not in conjunto_ordens_esperadas and 1 <= linha.ordemBloco <= len(blocos)
            for linha in matriz.linhas
        )
    )
    linhas_normalizadas: list[MatrizLinha] = []

    for linha in matriz.linhas:
        ordem_recebida = linha.ordemBloco
        if resposta_usa_indices_locais and 1 <= ordem_recebida <= len(blocos):
            linhas_normalizadas.append(linha.model_copy(update={"ordemBloco": ordens_esperadas[ordem_recebida - 1]}))
        elif ordem_recebida in conjunto_ordens_esperadas:
            linhas_normalizadas.append(linha)
        else:
            logger.info(
                "Descartando linha da IA com ordemBloco inexistente ordem=%s esperadas=%s",
                ordem_recebida,
                ordens_esperadas,
            )

    return MatrizOutput(linhas=linhas_normalizadas)


def _criar_linha_de_fallback(bloco: dict[str, Any]) -> MatrizLinha:
    orientacao = bloco.get("orientacao_parser") or {}
    tipo_tarefa = orientacao.get("tipoTarefa") or _TIPOS_TAREFA_POR_CATEGORIA.get(
        bloco.get("categoria"), "Informação"
    )
    descricao = " ".join(str(bloco.get("texto") or "").split())
    if not descricao:
        descricao = "Bloco sem texto extraível no PDF."
    return MatrizLinha(ordemBloco=bloco["ordem"], descricao=descricao, tipoTarefa=tipo_tarefa)


def _converter_com_openai(prompt_usuario: dict[str, Any]) -> MatrizOutput:
    client = get_openai_client()
    if client is None:
        raise LLMConversionError("OPENAI_API_KEY não está configurada no backend.")

    try:
        response = client.responses.parse(
            model=get_settings().openai_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt_usuario, ensure_ascii=False)},
            ],
            text_format=MatrizOutput,
        )
        resultado = response.output_parsed
        if resultado is None:
            raise LLMConversionError("A OpenAI não retornou uma saída estruturada.")
        return MatrizOutput.model_validate(resultado)
    except LLMConversionError:
        raise
    except Exception as exc:
        raise LLMConversionError("Falha ao obter JSON estruturado da OpenAI.") from exc


def _solicitar_ollama_em_stream(
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    on_progress: OllamaProgressCallback | None,
) -> str:
    if on_progress:
        on_progress("conectando", 0, 0)

    partes_de_resposta: list[str] = []
    trechos_recebidos = 0
    caracteres_recebidos = 0
    ultimo_status_em = float("-inf")
    payload_com_stream = {**payload, "stream": True}

    with httpx.stream("POST", endpoint, json=payload_com_stream, timeout=timeout_seconds) as response:
        response.raise_for_status()
        if on_progress:
            on_progress("aguardando_resposta", 0, 0)
        for linha in response.iter_lines():
            dados = linha.removeprefix("data: ").strip() if linha.startswith("data: ") else linha.strip()
            if not dados:
                continue
            if dados == "[DONE]":
                break

            evento = json.loads(dados)
            if not isinstance(evento, dict):
                continue
            if "error" in evento:
                raise LLMConversionError(f"Ollama retornou um erro: {evento['error']}")

            escolhas = evento.get("choices", [])
            if not escolhas:
                continue
            primeira_escolha = escolhas[0]
            delta = primeira_escolha.get("delta") or primeira_escolha.get("message") or {}
            if not isinstance(delta, dict):
                continue
            conteudo = delta.get("content") or ""
            raciocinio = delta.get("reasoning_content") or delta.get("reasoning") or ""
            agora = time.monotonic()

            if raciocinio and on_progress and agora - ultimo_status_em >= 1:
                on_progress("raciocinando", trechos_recebidos, caracteres_recebidos)
                ultimo_status_em = agora
            if not conteudo:
                continue

            partes_de_resposta.append(conteudo)
            trechos_recebidos += 1
            caracteres_recebidos += len(conteudo)
            if on_progress and (trechos_recebidos == 1 or agora - ultimo_status_em >= 1):
                on_progress("gerando_resposta", trechos_recebidos, caracteres_recebidos)
                ultimo_status_em = agora

    if on_progress:
        on_progress("resposta_completa", trechos_recebidos, caracteres_recebidos)
    return "".join(partes_de_resposta)


def _converter_com_ollama(
    prompt_usuario: dict[str, Any], on_progress: OllamaProgressCallback | None = None
) -> MatrizOutput:
    settings = get_settings()
    endpoint = f"{settings.ollama_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{JSON_OUTPUT_INSTRUCTION}"},
            {"role": "user", "content": json.dumps(prompt_usuario, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    try:
        content = _solicitar_ollama_em_stream(endpoint, payload, settings.ollama_timeout_seconds, on_progress)
        try:
            return _matriz_de_conteudo_json(content)
        except LLMConversionError:
            if on_progress:
                on_progress("corrigindo_formato", 0, 0)
            retry_payload = {
                **payload,
                "messages": [
                    *payload["messages"],
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": JSON_RETRY_INSTRUCTION},
                ],
            }
            retry_content = _solicitar_ollama_em_stream(
                endpoint, retry_payload, settings.ollama_timeout_seconds, on_progress
            )
            return _matriz_de_conteudo_json(retry_content)
    except httpx.ConnectError as exc:
        raise LLMConversionError(
            "Ollama não está disponível. Inicie o Ollama e execute o download do modelo configurado."
        ) from exc
    except (httpx.HTTPError, AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.exception("Falha ao processar a resposta em streaming do Ollama.")
        raise LLMConversionError("Falha ao obter JSON estruturado do Ollama.") from exc


def _converter_prompt(
    prompt_usuario: dict[str, Any], on_progress: OllamaProgressCallback | None = None
) -> MatrizOutput:
    if get_settings().llm_provider == "ollama":
        return _converter_com_ollama(prompt_usuario, on_progress)
    return _converter_com_openai(prompt_usuario)


def converter_blocos_com_ia(
    blocos: list[dict[str, Any]],
    regras_parser: list[dict[str, Any]],
    exemplos_parser: list[dict[str, Any]],
    contexto: dict[str, Any],
    on_progress: OllamaProgressCallback | None = None,
) -> list[dict[str, str]]:
    """Converte um lote pelo provedor de IA configurado."""
    prompt_usuario = _criar_prompt(blocos, regras_parser, exemplos_parser, contexto)
    matriz = _normalizar_ordens_da_resposta(blocos, _converter_prompt(prompt_usuario, on_progress))

    blocos_sem_saida = _obter_blocos_sem_saida(blocos, matriz)
    if blocos_sem_saida:
        if on_progress:
            on_progress("corrigindo_cobertura", 0, 0)
        prompt_correcao = _criar_prompt(blocos_sem_saida, regras_parser, exemplos_parser, contexto)
        prompt_correcao["instrucao"] = COVERAGE_RETRY_INSTRUCTION
        matriz_correcao = _normalizar_ordens_da_resposta(
            blocos_sem_saida,
            _converter_prompt(prompt_correcao, on_progress),
        )
        matriz = MatrizOutput(linhas=[*matriz.linhas, *matriz_correcao.linhas])

    blocos_sem_saida = _obter_blocos_sem_saida(blocos, matriz)
    for bloco_sem_saida in blocos_sem_saida:
        if on_progress:
            on_progress("corrigindo_cobertura", 0, 0)
        prompt_individual = _criar_prompt([bloco_sem_saida], regras_parser, exemplos_parser, contexto)
        prompt_individual["instrucao"] = COVERAGE_RETRY_INSTRUCTION
        matriz_individual = _normalizar_ordens_da_resposta(
            [bloco_sem_saida],
            _converter_prompt(prompt_individual, on_progress),
        )
        matriz = MatrizOutput(linhas=[*matriz.linhas, *matriz_individual.linhas])

    blocos_sem_saida = _obter_blocos_sem_saida(blocos, matriz)
    if blocos_sem_saida:
        logger.warning(
            "IA não retornou saída para blocos após recuperação; aplicando fallback do parser ordens=%s",
            [bloco["ordem"] for bloco in blocos_sem_saida],
        )
        matriz = MatrizOutput(
            linhas=[*matriz.linhas, *[_criar_linha_de_fallback(bloco) for bloco in blocos_sem_saida]]
        )

    _validar_cobertura_dos_blocos(blocos, matriz)
    return [linha.model_dump() for linha in matriz.linhas if linha.descricao.strip()]
