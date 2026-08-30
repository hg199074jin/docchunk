import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from docchunk.adapters.base import (
    DocumentAdapter,
    NormalizedBlock,
    NormalizedDocument,
    normalize_line_endings,
)
from docchunk.config import resolve_mineru_command
from docchunk.errors import ExternalToolError
from docchunk.models.pdf import PageFragment
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

    def _run_mineru(
        self,
        path: Path,
        *,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> Path:
        if (start_page is None) != (end_page is None):
            raise ValueError("start_page and end_page must be provided together")
        if start_page is not None and (start_page < 0 or end_page is None or end_page < start_page):
            raise ValueError("MinerU page range must be non-negative and ordered")

        output_root = Path(tempfile.mkdtemp(prefix="docchunk-mineru-"))
        command = [
            self.command,
            "-p", str(path),
            "-o", str(output_root),
            "-b", self.backend,
            "--effort", self.effort,
        ]
        if start_page is not None and end_page is not None:
            command.extend(["--start", str(start_page), "--end", str(end_page)])

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:
            shutil.rmtree(output_root, ignore_errors=True)
            raise ExternalToolError("MinerU executable was not found") from exc

        if result.returncode != 0:
            shutil.rmtree(output_root, ignore_errors=True)
            raise ExternalToolError(f"MinerU failed: {result.stderr.strip()}")

        return output_root

    def prepare(self, path: Path) -> NormalizedDocument:
        output_root = self._run_mineru(path)
        try:
            text, aligned_blocks, parsed_count = self._read_output(path, output_root)
            return NormalizedDocument(
                source_path=path,
                media_type="text/markdown",
                text=text,
                blocks=aligned_blocks,
                metadata={
                    "adapter": "mineru",
                    "backend": self.backend,
                    "effort": self.effort,
                    "parsed_blocks": parsed_count,
                    "aligned_blocks": len(aligned_blocks),
                    "unaligned_blocks": parsed_count - len(aligned_blocks),
                },
            )
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def prepare_page(self, path: Path, page_idx: int) -> PageFragment:
        if page_idx < 0:
            raise ValueError("page_idx must be >= 0")
        output_root = self._run_mineru(path, start_page=page_idx, end_page=page_idx)
        try:
            text, aligned_blocks, parsed_count = self._read_output(path, output_root)
            # MinerU can report a local page index for a range-limited run. The
            # original PDF page is authoritative for SmartPdf provenance.
            aligned_blocks = [
                block.model_copy(update={"page_idx": page_idx})
                for block in aligned_blocks
            ]
            if text and not aligned_blocks:
                aligned_blocks = [
                    NormalizedBlock(
                        block_index=0,
                        char_start=0,
                        char_end=len(text),
                        text=text,
                        page_idx=page_idx,
                    )
                ]
            return PageFragment(
                page_idx=page_idx,
                markdown=text,
                blocks=aligned_blocks,
                parser="mineru",
                route_reason="needs_ocr",
                metadata={
                    "backend": self.backend,
                    "effort": self.effort,
                    "parsed_blocks": parsed_count,
                    "aligned_blocks": len(aligned_blocks),
                    "unaligned_blocks": parsed_count - len(aligned_blocks),
                },
            )
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    @staticmethod
    def _read_output(path: Path, output_root: Path) -> tuple[str, list[NormalizedBlock], int]:
        # 按字面文件名匹配而不是 glob pattern：文件名里的 [ ] ? *
        # 在 rglob pattern 中是元字符，会导致输出永远找不到
        # （v1.0.2 回归：《一本小小的蓝色逻辑书 (...) [译]》.pdf）。
        markdown_files: list[Path] = []
        content_files: list[Path] = []
        for item in output_root.rglob("*"):
            if not item.is_file():
                continue
            if item.name == f"{path.stem}.md":
                markdown_files.append(item)
            elif item.name.startswith(f"{path.stem}_content_list") and item.suffix == ".json":
                # 兼容 v1/v2 命名：*_content_list.json / *_content_list_v2.json
                content_files.append(item)

        markdown_files.sort()
        content_files.sort()

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

        return text, aligned_blocks, len(parsed_blocks)
