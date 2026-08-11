from typing import Literal

from pydantic import BaseModel, Field


TipoTarefa = Literal["Padrão/Anexo", "Título/Subtítulo", "Informação", "Execução", "Ignorar"]


class MatrizLinha(BaseModel):
    ordemBloco: int = Field(ge=1)
    itemPadrao: str = ""
    descricao: str = ""
    tipoTarefa: TipoTarefa
    subtarefaHTA: str = ""
    descricaoTarefa: str = ""


class MatrizOutput(BaseModel):
    linhas: list[MatrizLinha]
