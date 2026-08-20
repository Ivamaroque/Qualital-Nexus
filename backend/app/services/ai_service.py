import json
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.models.schemas import BlockType, ParsedBlock

logger = logging.getLogger(__name__)


async def normalize_complex_blocks(blocks: list[ParsedBlock], examples: list[dict[str, Any]], settings: Settings) -> list[ParsedBlock]:
    """Normaliza somente blocos explicitamente marcados como ambíguos pelo parser.

    Sem chave do OpenRouter, ou em falhas externas, preserva exatamente o resultado
    determinístico. A chamada usa o endpoint Chat Completions do OpenRouter sem depender de SDK externo.
    """
    targets = [block for block in blocks if block.needs_ai]
    if not targets:
        return blocks
    if not settings.openrouter_api_key:
        logger.info("OpenRouter não configurado; %d blocos seguem com parser determinístico.", len(targets))
        return blocks

    prompt = {
        "task": "Classifique cada bloco como Título, Subtítulo, Execução ou Informação. Não invente conteúdo.",
        "examples": examples,
        "blocks": [{"index": index, "content": block.content, "current_type": block.block_type.value} for index, block in enumerate(targets)],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=_openrouter_headers(settings),
                json={
                    "model": settings.openrouter_model,
                    "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Normalização via OpenRouter falhou; usando parser determinístico.", exc_info=True)
        return blocks

    try:
        output_text = result["choices"][0]["message"]["content"]
        classifications = json.loads(output_text).get("classifications", [])
        allowed = {item.value for item in BlockType}
        for item in classifications:
            index, block_type = item.get("index"), item.get("type")
            if isinstance(index, int) and 0 <= index < len(targets) and block_type in allowed:
                targets[index].block_type = BlockType(block_type)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Resposta do OpenRouter não pôde ser interpretada; usando parser determinístico.", exc_info=True)
    return blocks


def _openrouter_headers(settings: Settings) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    if settings.openrouter_http_referer:
        headers["HTTP-Referer"] = settings.openrouter_http_referer
    if settings.openrouter_app_title:
        headers["X-OpenRouter-Title"] = settings.openrouter_app_title
    return headers
