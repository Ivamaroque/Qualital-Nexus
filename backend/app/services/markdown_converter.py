import re

from app.utils.text_utils import normalize_multiline_text


def text_to_markdown(text: str) -> str:
    """Normaliza o texto extraído em uma representação Markdown leve e estável."""
    lines: list[str] = []
    for raw_line in normalize_multiline_text(text).splitlines():
        line = raw_line.strip()
        if re.match(r"^\d+\.\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ ]{3,}$", line):
            lines.append(f"## {line}")
        else:
            lines.append(line)
    return "\n".join(lines)
