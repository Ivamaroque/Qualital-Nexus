from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings


@lru_cache
def get_openai_client() -> OpenAI | None:
    """Cria o cliente somente quando a chave estiver configurada."""
    api_key = get_settings().openai_api_key
    return OpenAI(api_key=api_key) if api_key else None
