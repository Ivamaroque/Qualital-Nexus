import re
import unicodedata


def normalize_whitespace(value: str) -> str:
    value = value.replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def normalize_multiline_text(value: str) -> str:
    lines = (normalize_whitespace(line) for line in value.splitlines())
    return "\n".join(line for line in lines if line)


def normalized_for_match(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return normalize_whitespace(value).upper()


def item_hierarchy(value: str) -> str:
    match = re.match(r"^(\d+(?:\.\d+){0,5})\.?\s+", value)
    return match.group(1) if match else ""


def remove_item_number(value: str) -> str:
    return re.sub(r"^\d+(?:\.\d+){0,5}\.?\s+", "", value).strip()
