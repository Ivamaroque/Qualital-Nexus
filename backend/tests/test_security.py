import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import require_authenticated_user


def _request(authorization: str = "") -> SimpleNamespace:
    return SimpleNamespace(headers={"Authorization": authorization} if authorization else {})


def _executar_sem_espera(corrotina):
    try:
        corrotina.send(None)
    except StopIteration as resultado:
        return resultado.value
    raise AssertionError("O cenário unitário não deveria iniciar uma operação assíncrona.")


class SecurityTest(unittest.TestCase):
    def test_local_mode_allows_request_when_auth_is_optional(self):
        settings = SimpleNamespace(
            auth_required=False,
            supabase_auth_is_configured=False,
        )
        with patch("app.core.security.get_settings", return_value=settings):
            user = _executar_sem_espera(require_authenticated_user(_request()))

        self.assertIsNone(user)

    def test_required_auth_without_supabase_returns_service_unavailable(self):
        settings = SimpleNamespace(
            auth_required=True,
            supabase_auth_is_configured=False,
        )
        with patch("app.core.security.get_settings", return_value=settings):
            with self.assertRaises(HTTPException) as context:
                _executar_sem_espera(require_authenticated_user(_request()))

        self.assertEqual(context.exception.status_code, 503)

    def test_configured_auth_requires_bearer_token(self):
        settings = SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-key",
            supabase_auth_is_configured=True,
        )
        with patch("app.core.security.get_settings", return_value=settings):
            with self.assertRaises(HTTPException) as context:
                _executar_sem_espera(require_authenticated_user(_request()))

        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
