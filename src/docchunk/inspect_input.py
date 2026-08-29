from pathlib import Path

from docchunk.adapters.base import DocumentAdapter
from docchunk.adapters.markdown import MarkdownAdapter
from docchunk.adapters.mineru import MinerUAdapter
from docchunk.adapters.pandoc import PandocAdapter
from docchunk.adapters.text import TextAdapter
from docchunk.errors import UnsupportedInputError


def choose_adapter(
    path: Path,
    mineru_command: str = "mineru",
    mineru_backend: str = "hybrid-engine",
    mineru_effort: str = "medium",
) -> DocumentAdapter:
    suffix = path.suffix.casefold()

    if suffix in {".md", ".markdown"}:
        return MarkdownAdapter()
    if suffix == ".txt":
        return TextAdapter()
    if suffix == ".docx":
        return PandocAdapter()
    if suffix == ".pdf":
        return MinerUAdapter(
            command=mineru_command,
            backend=mineru_backend,
            effort=mineru_effort,
        )

    raise UnsupportedInputError(f"Unsupported input type: {suffix or '<none>'}")
