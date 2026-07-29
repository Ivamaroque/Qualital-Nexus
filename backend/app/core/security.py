import logging

import httpx
from fastapi import HTTPException, Request, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def require_authenticated_user(request: Request) -> dict | None:
    """Valida o JWT pelo endpoint oficial do Supabase.

    Em desenvolvimento sem credenciais do Supabase, a autenticação pode ficar
    desabilitada por ``AUTH_REQUIRED=false``. Isso evita aceitar tokens sem
    validação em uma instalação configurada.
    """

    settings: Settings = get_settings()
    authorization = request.headers.get("Authorization", "")

    if not settings.supabase_is_configured:
        if settings.auth_required:
            logger.error("AUTH_REQUIRED=true sem credenciais do Supabase configuradas")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Autenticação Supabase não está configurada no servidor.",
            )
        logger.warning("Autenticação desabilitada: Supabase não configurado (modo local).")
        return None

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Bearer do Supabase é obrigatório.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    base_url = settings.supabase_url.rstrip("/")
    if base_url.endswith("/rest/v1"):
        base_url = base_url[: -len("/rest/v1")]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{base_url}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key or "",
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        logger.exception("Não foi possível validar o token no Supabase")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível validar a sessão agora.",
        ) from exc

    if response.status_code != status.HTTP_200_OK:
        logger.info("Token Supabase rejeitado: status=%s", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Supabase inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = response.json()
    logger.info("Token Supabase validado para user_id=%s", user.get("id"))
    return user
