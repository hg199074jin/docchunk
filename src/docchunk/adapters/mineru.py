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

    def _run_mineru(
        self,
        path: Path,
        *,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> Path:
        """Run MinerU once and return its (temporary) output root.

        ``start_page`` / ``end_page`` map to the official CLI's 0-based,
        end-inclusive ``--start`` / ``--end`` flags. The temporary output root
        is removed on every failure branch; the caller removes it after a
        successful run.
        """
        output_root = Path(tempfile.mkdtemp(prefix="docchunk-mineru-"))

        try:
            args = [
                self.command,
                "-p", str(path),
                "-o", str(output_root),
                "-b", self.backend,
                "--effort", self.effort,
            ]
            if start_page is not None:
                args.extend(["--start", str(start_page)])
            if end_page is not None:
                args.extend(["--end", str(end_page)])

            try:
                result = subprocess.run(
                    args,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
            except FileNotFoundError as exc:
                raise ExternalToolError("MinerU executable was not found") from exc

            if result.returncode != 0:
                raise ExternalToolError(f"MinerU failed: {result.stderr.strip()}")
        except Exception:
            # 失败分支同样必须清理，否则错误重试会在临时目录里永久堆积。
            shutil.rmtree(output_root, ignore_errors=True)
            raise

        return output_root

    def prepare(self, path: Path) -> NormalizedDocument:
        output_root = self._run_mineru(path)
        try:
            return self._load_output_document(path, output_root)
        finally:
            # 设计 §24：原始资料保护 + 隐私边界——MinerU 临时目录里含 OCR
            # 中间产物与可能的图像，必须在 adapter 层自动清理；不显式保留
            # 就意味着"重生可获得"，与设计一致。
            shutil.rmtree(output_root, ignore_errors=True)

    def prepare_page(self, path: Path, page_idx: int) -> NormalizedDocument:
        """Parse exactly one page of the original PDF (no physical splitting).

        All resulting blocks are force-stamped with the original PDF's
        ``page_idx`` — MinerU's own page numbering for ranged output is never
        trusted (design §17).
        """
        if page_idx < 0:
            raise ValueError("page_idx must be >= 0")

        output_root = self._run_mineru(path, start_page=page_idx, end_page=page_idx)
        try:
            document = self._load_output_document(path, output_root)
            blocks = [
                block.model_copy(update={"page_idx": page_idx})
                for block in document.blocks
            ]
            metadata = dict(document.metadata)
            metadata.update(
                {
                    "page_mode": True,
                    "source_page_idx": page_idx,
                }
            )
            return document.model_copy(update={"blocks": blocks, "metadata": metadata})
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def _load_output_document(self, path: Path, output_root: Path) -> NormalizedDocument:
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
