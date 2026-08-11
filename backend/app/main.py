import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers.extracao_pdf import router as extracao_pdf_router


class StatusPollingAccessFilter(logging.Filter):
    """Oculta apenas as consultas bem-sucedidas e repetitivas do progresso."""

    def filter(self, record: logging.LogRecord) -> bool:
        mensagem = record.getMessage()
        is_status_polling = "GET /api/extracao-pdf/process/" in mensagem and "/status HTTP" in mensagem
        return not (is_status_polling and '" 200' in mensagem)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(filtro, StatusPollingAccessFilter) for filtro in access_logger.filters):
        access_logger.addFilter(StatusPollingAccessFilter())
    logging.getLogger(__name__).info("Iniciando %s em ambiente=%s", settings.app_name, settings.environment)
    yield


settings = get_settings()
app = FastAPI(title="Qualital Nexus API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Processing-Id"],
)
app.include_router(extracao_pdf_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
