from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from docchunk.doctor import run_doctor


def test_doctor_reports_missing_pandoc() -> None:
    with patch("docchunk.doctor.shutil.which") as which:
        which.side_effect = lambda name: None if name == "pandoc" else f"/usr/bin/{name}"
        report = run_doctor()

    pandoc = next(item for item in report.checks if item.name == "pandoc")
    assert pandoc.ok is False
    assert "install" in pandoc.fix.lower()


def test_doctor_checks_pdf_inspector() -> None:
    report = run_doctor()

    check = next(item for item in report.checks if item.name == "pdf-inspector")
    assert check.ok is True
    assert check.detail.startswith("1.")
    # 检查顺序：pdf-inspector 在 python 之后、pandoc 之前（设计 §38）
    names = [item.name for item in report.checks]
    assert names.index("pdf-inspector") < names.index("pandoc")


def test_doctor_reports_missing_pdf_inspector() -> None:
    with patch(
        "docchunk.doctor.package_version",
        side_effect=PackageNotFoundError("pdf-inspector"),
    ):
        report = run_doctor()

    check = next(item for item in report.checks if item.name == "pdf-inspector")
    assert check.ok is False


def test_doctor_all_ok_reports_true() -> None:
    report = run_doctor()
    assert report.ok is True
    assert {check.name for check in report.checks} >= {
        "python",
        "pdf-inspector",
        "pandoc",
        "mineru",
        "tiktoken",
        "corpus_root",
    }
