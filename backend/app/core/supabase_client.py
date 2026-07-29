from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


@lru_cache
def get_supabase_client() -> Client | None:
    """Retorna o cliente de serviço exclusivo do backend, quando configurado."""
    settings = get_settings()
    if not settings.supabase_is_configured:
        return None
    return create_client(settings.supabase_url or "", settings.supabase_service_role_key or "")
