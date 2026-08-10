import json
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.openai_client import get_openai_client
from app.schemas.matriz import MatrizOutput

SYSTEM_PROMPT = (
    "Você é um conversor técnico do Qualital Nexus. Sua função é converter blocos de PDFs "
    "técnicos em linhas para a Matriz de Priorização. Siga as regras do parser, os exemplos "
    "RAG e preserve a granularidade do documento. Não invente conteúdo. Não resuma "
    "excessivamente. Não crie linhas para cabeçalho, rodapé, página, INTERNA ou aprovação. "
    "Retorne somente um objeto JSON compatível com o schema solicitado."
)


class LLMConversionError(RuntimeError):
    """Erro previsível ao transformar blocos com um provedor de IA."""


def _criar_prompt(
    blocos: list[dict[str, Any]],
    regras_parser: list[dict[str, Any]],
    exemplos_rag: list[dict[str, Any]],
    contexto: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contexto_arquivo": contexto.get("filename", ""),
        "file_order": contexto.get("file_order"),
        "instrucao": "Converta os blocos na ordem recebida e preserve a granularidade de cada bloco.",
        "regras_parser": regras_parser,
        "exemplos_rag": exemplos_rag,
        "blocos": blocos,
    }


def _matriz_de_conteudo_json(conteudo: str) -> MatrizOutput:
    texto = conteudo.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", maxsplit=1)[1].rsplit("```", maxsplit=1)[0].strip()
    return MatrizOutput.model_validate_json(texto)


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


def _converter_com_ollama(prompt_usuario: dict[str, Any]) -> MatrizOutput:
    settings = get_settings()
    endpoint = f"{settings.ollama_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt_usuario, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    try:
        response = httpx.post(endpoint, json=payload, timeout=settings.ollama_timeout_seconds)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _matriz_de_conteudo_json(content)
    except httpx.ConnectError as exc:
        raise LLMConversionError(
            "Ollama não está disponível. Inicie o Ollama e execute o download do modelo configurado."
        ) from exc
    except (httpx.HTTPError, AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMConversionError("Falha ao obter JSON estruturado do Ollama.") from exc


def converter_blocos_com_ia(
    blocos: list[dict[str, Any]],
    regras_parser: list[dict[str, Any]],
    exemplos_rag: list[dict[str, Any]],
    contexto: dict[str, Any],
) -> list[dict[str, str]]:
    """Converte um lote pelo provedor de IA configurado."""
    prompt_usuario = _criar_prompt(blocos, regras_parser, exemplos_rag, contexto)
    settings = get_settings()
    if settings.llm_provider == "ollama":
        matriz = _converter_com_ollama(prompt_usuario)
    else:
        matriz = _converter_com_openai(prompt_usuario)

    return [linha.model_dump() for linha in matriz.linhas if linha.descricao.strip()]
