import json
import shutil
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
        try:
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

            return NormalizedDocument(
                source_path=path,
                media_type="text/markdown",
                text=text,
                blocks=aligned_blocks,
                metadata={
                    "adapter": "mineru",
                    "backend": self.backend,
                    "effort": self.effort,
                    "parsed_blocks": len(parsed_blocks),
                    "aligned_blocks": len(aligned_blocks),
                    "unaligned_blocks": len(parsed_blocks) - len(aligned_blocks),
                },
            )
        finally:
            # 设计 §24：原始资料保护 + 隐私边界——MinerU 临时目录里含 OCR
            # 中间产物与可能的图像，必须在 adapter 层自动清理；不显式保留
            # 就意味着"重生可获得"，与设计一致。失败分支也必须清理，否则
            # 错误重试会在 /var/folders 下永久堆积。
            shutil.rmtree(output_root, ignore_errors=True)
