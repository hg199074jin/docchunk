import json
import subprocess
import tempfile
from pathlib import Path

from docchunk.adapters.base import DocumentAdapter, NormalizedDocument, normalize_line_endings
from docchunk.config import resolve_mineru_command
from docchunk.errors import ExternalToolError
from docchunk.provenance.mineru import align_blocks_to_markdown, parse_content_list


class MinerUAdapter(DocumentAdapter):
    def __init__(
        self,
        command: str = "mineru",
        backend: str = "hybrid-engine",
        effort: str = "medium",
    ) -> None:
        self.command = resolve_mineru_command(command)
        self.backend = backend
        self.effort = effort

    def _run_mineru(self, path: Path) -> Path:
        output_root = Path(tempfile.mkdtemp(prefix="docchunk-mineru-"))

        try:
            result = subprocess.run(
                [
                    self.command,
                    "-p", str(path),
                    "-o", str(output_root),
                    "-b", self.backend,
                    "--effort", self.effort,
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:
            raise ExternalToolError("MinerU executable was not found") from exc

        if result.returncode != 0:
            raise ExternalToolError(f"MinerU failed: {result.stderr.strip()}")

        return output_root

    def prepare(self, path: Path) -> NormalizedDocument:
        output_root = self._run_mineru(path)
        markdown_files = sorted(output_root.rglob(f"{path.stem}.md"))
        # 兼容 v1/v2 命名：*_content_list.json / *_content_list_v2.json
        content_files = sorted(output_root.rglob(f"{path.stem}_content_list*.json"))

        if not markdown_files:
            raise ExternalToolError("MinerU completed but no Markdown output was found")

        markdown_path = markdown_files[0]
        text = normalize_line_endings(markdown_path.read_text(encoding="utf-8"))

        parsed_blocks = []
        aligned_blocks = []
        if content_files:
            raw = json.loads(content_files[0].read_text(encoding="utf-8"))
            if isinstance(raw, list):
                parsed_blocks = parse_content_list(raw)
                aligned_blocks = align_blocks_to_markdown(text, parsed_blocks)

        return NormalizedDocument(
            source_path=path,
            media_type="text/markdown",
            text=text,
            blocks=aligned_blocks,
            metadata={
                "adapter": "mineru",
                "mineru_output_root": str(output_root),
                "parsed_blocks": len(parsed_blocks),
                "aligned_blocks": len(aligned_blocks),
                "unaligned_blocks": len(parsed_blocks) - len(aligned_blocks),
            },
        )
