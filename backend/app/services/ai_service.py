import json
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.models.schemas import BlockType, ParsedBlock

logger = logging.getLogger(__name__)


async def normalize_complex_blocks(blocks: list[ParsedBlock], examples: list[dict[str, Any]], settings: Settings) -> list[ParsedBlock]:
    """Normaliza somente blocos explicitamente marcados como ambíguos pelo parser.

    Sem chave da OpenAI, ou em falhas externas, preserva exatamente o resultado
    determinístico. A chamada usa a API Responses sem depender do SDK Python.
    """
    targets = [block for block in blocks if block.needs_ai]
    if not targets:
        return blocks
    if not settings.openai_api_key:
        logger.info("OpenAI não configurada; %d blocos seguem com parser determinístico.", len(targets))
        return blocks

    prompt = {
        "task": "Classifique cada bloco como Título, Subtítulo, Execução ou Informação. Não invente conteúdo.",
        "examples": examples,
        "blocks": [{"index": index, "content": block.content, "current_type": block.block_type.value} for index, block in enumerate(targets)],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "input": json.dumps(prompt, ensure_ascii=False),
                    "text": {"format": {"type": "json_object"}},
                },
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Normalização OpenAI falhou; usando parser determinístico.", exc_info=True)
        return blocks

    try:
        output_text = result["output"][0]["content"][0]["text"]
        classifications = json.loads(output_text).get("classifications", [])
        allowed = {item.value for item in BlockType}
        for item in classifications:
            index, block_type = item.get("index"), item.get("type")
            if isinstance(index, int) and 0 <= index < len(targets) and block_type in allowed:
                targets[index].block_type = BlockType(block_type)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Resposta OpenAI não pôde ser interpretada; usando parser determinístico.", exc_info=True)
    return blocks
