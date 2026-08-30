import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from pydantic import BaseModel

from docchunk.config import AppConfig, resolve_mineru_command
from docchunk.tokenizer import TokenCounter


class DoctorCheck(BaseModel):
    name: str
    ok: bool
    detail: str
    fix: str = ""


class DoctorReport(BaseModel):
    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.checks)


def _check_python() -> DoctorCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = (3, 12) <= sys.version_info[:2] < (3, 13)
    return DoctorCheck(
        name="python",
        ok=ok,
        detail=version,
        fix="" if ok else "Install Python 3.12 (uv python install 3.12)",
    )


def _check_pandoc() -> DoctorCheck:
    path = shutil.which("pandoc")
    if not path:
        return DoctorCheck(
            name="pandoc",
            ok=False,
            detail="not found",
            fix="install with: brew install pandoc",
        )

    try:
        result = subprocess.run(
            [path, "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        version = result.stdout.splitlines()[0] if result.stdout else "unknown"
    except OSError as exc:
        return DoctorCheck(
            name="pandoc",
            ok=False,
            detail=f"cannot execute: {exc}",
            fix="install with: brew install pandoc",
        )

    return DoctorCheck(name="pandoc", ok=True, detail=f"{version} @ {path}")


def _check_pdf_inspector() -> DoctorCheck:
    try:
        import pdf_inspector

        version = package_version("pdf-inspector")
        return DoctorCheck(
            name="pdf-inspector",
            ok=True,
            detail=f"{version} @ {pdf_inspector.__file__}",
        )
    except (ImportError, PackageNotFoundError, OSError) as exc:
        return DoctorCheck(
            name="pdf-inspector",
            ok=False,
            detail=f"not available: {exc}",
            fix="run: uv sync",
        )


def _check_mineru(config: AppConfig) -> DoctorCheck:
    resolved = resolve_mineru_command(config.mineru_command)
    found = shutil.which("mineru")

    if resolved == "mineru":
        return DoctorCheck(
            name="mineru",
            ok=False,
            detail="command not found on PATH and no venv fallback",
            fix=(
                "verify the existing MinerU installation with:\n"
                "ls ~/.venvs/mineru/bin/mineru\n"
                "~/.venvs/mineru/bin/mineru --version\n"
                "or set mineru_command to the absolute path"
            ),
        )

    detail_bits = [f"resolved: {resolved}"]
    if found:
        detail_bits.append(f"PATH: {found}")

    try:
        result = subprocess.run(
            [resolved, "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        version = (result.stdout or result.stderr).strip().splitlines()
        detail_bits.append(version[0] if version else "unknown version")
    except OSError as exc:
        return DoctorCheck(
            name="mineru",
            ok=False,
            detail=f"cannot execute {resolved}: {exc}",
            fix="verify the existing MinerU installation and set mineru_command",
        )

    detail_bits.append(f"backend: {config.mineru_backend} / effort: {config.mineru_effort}")
    return DoctorCheck(name="mineru", ok=True, detail="; ".join(detail_bits))


def _check_tiktoken(config: AppConfig) -> DoctorCheck:
    try:
        counter = TokenCounter(config.tokenizer_encoding)
        sample = counter.count("验证")
        return DoctorCheck(
            name="tiktoken",
            ok=True,
            detail=f"{config.tokenizer_encoding} loaded (sample tokens={sample})",
        )
    except Exception as exc:  # noqa: BLE001 — 任何加载/网络失败都要变成可读诊断
        return DoctorCheck(
            name="tiktoken",
            ok=False,
            detail=f"cannot load {config.tokenizer_encoding}: {exc}",
            fix="check network access to openaipublic.blob.core.windows.net",
        )


def _check_corpus_root(config: AppConfig) -> DoctorCheck:
    root = config.corpus_root
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".docchunk-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return DoctorCheck(
            name="corpus_root",
            ok=False,
            detail=f"{root} is not writable: {exc}",
            fix="check the volume is mounted and writable, or pass --corpus-root",
        )

    return DoctorCheck(name="corpus_root", ok=True, detail=str(root))


def run_doctor(config: AppConfig | None = None) -> DoctorReport:
    config = config or AppConfig()
    return DoctorReport(
        checks=[
            _check_python(),
            _check_pandoc(),
            _check_pdf_inspector(),
            _check_mineru(config),
            _check_tiktoken(config),
            _check_corpus_root(config),
        ]
    )
