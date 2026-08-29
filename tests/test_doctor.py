from unittest.mock import patch

from docchunk.doctor import run_doctor


def test_doctor_reports_missing_pandoc() -> None:
    with patch("docchunk.doctor.shutil.which") as which:
        which.side_effect = lambda name: None if name == "pandoc" else f"/usr/bin/{name}"
        report = run_doctor()

    pandoc = next(item for item in report.checks if item.name == "pandoc")
    assert pandoc.ok is False
    assert "install" in pandoc.fix.lower()


def test_doctor_all_ok_reports_true() -> None:
    report = run_doctor()
    assert report.ok is True
    assert {check.name for check in report.checks} >= {
        "python",
        "pandoc",
        "mineru",
        "tiktoken",
        "corpus_root",
    }
