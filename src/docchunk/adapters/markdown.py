from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedDocument, normalize_line_endings


class MarkdownAdapter(DocumentAdapter):
    def prepare(self, path: Path) -> NormalizedDocument:
        text = normalize_line_endings(path.read_text(encoding="utf-8"))
        return NormalizedDocument(
            source_path=path,
            media_type="text/markdown",
            text=text,
        )
