import re
from pathlib import Path

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".markdown", ".txt"}


def _natural_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.name.casefold())
    return [int(part) if part.isdigit() else part for part in parts]


def discover_inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    if not path.is_dir():
        raise FileNotFoundError(path)

    files = [
        item
        for item in path.iterdir()
        if item.is_file() and item.suffix.casefold() in SUPPORTED_SUFFIXES
    ]
    return sorted(files, key=_natural_key)
