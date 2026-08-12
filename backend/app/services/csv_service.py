import csv
import io
from typing import Any

CSV_COLUMNS = (
    "Item (Padrão)",
    "Descrição",
    "Tipo da Tarefa",
    "ID da Subtarefa",
    "Subtarefa (HTA)",
    "Descrição da tarefa",
)


def _campo_csv(valor: Any) -> str:
    return "\n".join(
        " ".join(linha.split())
        for linha in str(valor or "").splitlines()
        if linha.strip()
    )


def gerar_csv_matriz(linhas: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, delimiter=";", lineterminator="\n")
    writer.writeheader()
    proximo_id = 1
    for linha in linhas:
        padrao_anexo = linha.get("tipoTarefa") == "Padrão/Anexo"
        identificador = "" if padrao_anexo else str(proximo_id)
        if not padrao_anexo:
            proximo_id += 1
        writer.writerow(
            {
                "Item (Padrão)": _campo_csv(linha.get("itemPadrao")),
                "Descrição": _campo_csv(linha.get("descricao")),
                "Tipo da Tarefa": _campo_csv(linha.get("tipoTarefa")),
                "ID da Subtarefa": identificador,
                "Subtarefa (HTA)": _campo_csv(linha.get("subtarefaHTA")),
                "Descrição da tarefa": _campo_csv(linha.get("descricaoTarefa")),
            }
        )
    return "\ufeff" + output.getvalue()
