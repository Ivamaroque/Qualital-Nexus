from typing import Any

_ALLOWED_TYPES = {"Padrão/Anexo", "Título/Subtítulo", "Informação", "Execução"}


def _normalizar_valor(valor: Any, preservar_quebras: bool = False) -> str:
    texto = str(valor or "")
    if not preservar_quebras:
        return " ".join(texto.split())
    return "\n".join(
        " ".join(linha.split())
        for linha in texto.splitlines()
        if linha.strip()
    )


def normalizar_linhas(linhas: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalizadas: list[dict[str, str]] = []
    vistas: set[tuple[str, str, str, str, str]] = set()
    for linha in linhas:
        descricao = _normalizar_valor(linha.get("descricao"), preservar_quebras=True)
        tipo = _normalizar_valor(linha.get("tipoTarefa"))
        if tipo == "Ignorar":
            continue
        if tipo not in _ALLOWED_TYPES:
            tipo = "Informação"
        item = _normalizar_valor(linha.get("itemPadrao"))
        if not descricao and not (tipo == "Padrão/Anexo" and item):
            continue
        subtarefa = _normalizar_valor(linha.get("subtarefaHTA"))
        descricao_tarefa = _normalizar_valor(linha.get("descricaoTarefa"), preservar_quebras=True)
        chave = (
            item,
            " ".join(descricao.split()),
            tipo,
            subtarefa,
            " ".join(descricao_tarefa.split()),
        )
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
