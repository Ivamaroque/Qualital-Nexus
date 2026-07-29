from typing import Any

_ALLOWED_TYPES = {"Padrão/Anexo", "Título/Subtítulo", "Informação", "Execução"}


def _normalizar_valor(valor: Any) -> str:
    return " ".join(str(valor or "").split())


def normalizar_linhas(linhas: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalizadas: list[dict[str, str]] = []
    vistas: set[tuple[str, str, str, str, str]] = set()
    for linha in linhas:
        descricao = _normalizar_valor(linha.get("descricao"))
        tipo = _normalizar_valor(linha.get("tipoTarefa"))
        if not descricao or tipo == "Ignorar":
            continue
        if tipo not in _ALLOWED_TYPES:
            tipo = "Informação"
        item = _normalizar_valor(linha.get("itemPadrao"))
        subtarefa = _normalizar_valor(linha.get("subtarefaHTA"))
        descricao_tarefa = _normalizar_valor(linha.get("descricaoTarefa"))
        chave = (item, descricao, tipo, subtarefa, descricao_tarefa)
        if chave in vistas:
            continue
        vistas.add(chave)
        normalizadas.append(
            {
                "itemPadrao": item,
                "descricao": descricao,
                "tipoTarefa": tipo,
                "subtarefaHTA": subtarefa,
                "descricaoTarefa": descricao_tarefa,
            }
        )
    return normalizadas
