import csv
import io

from app.models.schemas import ParsedBlock

CSV_COLUMNS = ("ordem_arquivo", "arquivo", "tipo_documento", "ordem_bloco", "tipo", "seção", "hierarquia", "conteúdo")


def generate_csv(blocks: list[ParsedBlock]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for block in blocks:
        writer.writerow(
            {
                "ordem_arquivo": block.file_order,
                "arquivo": block.filename,
                "tipo_documento": block.document_type,
                "ordem_bloco": block.block_order,
                "tipo": block.block_type.value,
                "seção": block.section,
                "hierarquia": block.hierarchy,
                "conteúdo": block.content,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
