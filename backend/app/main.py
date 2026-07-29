import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers.extracao_pdf import router as extracao_pdf_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger(__name__).info("Iniciando %s em ambiente=%s", settings.app_name, settings.environment)
    yield


settings = get_settings()
app = FastAPI(title="Qualital Nexus API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(extracao_pdf_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
