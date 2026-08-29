import subprocess
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedDocument, normalize_line_endings
from docchunk.errors import ExternalToolError


class PandocAdapter(DocumentAdapter):
    def prepare(self, path: Path) -> NormalizedDocument:
        try:
            result = subprocess.run(
                ["pandoc", str(path), "-f", "docx", "-t", "gfm"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:
            raise ExternalToolError("Pandoc executable was not found") from exc

        if result.returncode != 0:
            raise ExternalToolError(f"Pandoc failed: {result.stderr.strip()}")

        return NormalizedDocument(
            source_path=path,
            media_type="text/markdown",
            text=normalize_line_endings(result.stdout),
            metadata={"adapter": "pandoc"},
        )
