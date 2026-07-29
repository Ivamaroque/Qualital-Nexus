import json
from typing import Any

from app.core.config import get_settings
from app.core.openai_client import get_openai_client
from app.schemas.matriz import MatrizOutput

SYSTEM_PROMPT = (
    "Você é um conversor técnico do Qualital Nexus. Sua função é converter blocos de PDFs "
    "técnicos em linhas para a Matriz de Priorização. Siga as regras do parser, os exemplos "
    "RAG e preserve a granularidade do documento. Não invente conteúdo. Não resuma "
    "excessivamente. Não crie linhas para cabeçalho, rodapé, página, INTERNA ou aprovação. "
    "Retorne somente JSON no schema solicitado."
)


class LLMConversionError(RuntimeError):
    """Erro previsível ao transformar um bloco com a OpenAI."""


def converter_blocos_com_gpt(
    blocos: list[dict[str, Any]],
    regras_parser: list[dict[str, Any]],
    exemplos_rag: list[dict[str, Any]],
    contexto: dict[str, Any],
) -> list[dict[str, str]]:
    """Converte um lote via Responses API com validação Pydantic estruturada."""
    client = get_openai_client()
    if client is None:
        raise LLMConversionError("OPENAI_API_KEY não está configurada no backend.")

    prompt_usuario = {
        "contexto_arquivo": contexto.get("filename", ""),
        "file_order": contexto.get("file_order"),
        "instrucao": "Converta os blocos na ordem recebida e preserve a granularidade de cada bloco.",
        "regras_parser": regras_parser,
        "exemplos_rag": exemplos_rag,
        "blocos": blocos,
    }
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
        matriz = MatrizOutput.model_validate(resultado)
    except LLMConversionError:
        raise
    except Exception as exc:
        raise LLMConversionError("Falha ao obter JSON estruturado da OpenAI.") from exc

    return [linha.model_dump() for linha in matriz.linhas if linha.descricao.strip()]
