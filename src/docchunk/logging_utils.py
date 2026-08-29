import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class EventLogger:
    """结构化 JSONL 事件日志；禁止写入文档全文。"""

    def __init__(
        self,
        path: Path | None,
        echo: bool = False,
    ) -> None:
        self.path = path
        self.echo = echo

    def log(
        self,
        stage: str,
        status: str,
        message: str,
        *,
        document_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.path is None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        event: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "stage": stage,
            "status": status,
            "message": message,
        }
        if document_id is not None:
            event["document_id"] = document_id
        if extra:
            event.update(extra)

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False))
            handle.write("\n")

        if self.echo:
            print(f"[{stage}] {status}: {message}")

    def tool_error(
        self,
        stage: str,
        exc: BaseException,
    ) -> None:
        """失败事件必须持久化外部工具 stderr（设计 §22.1），并截断防止日志膨胀。"""
        detail = f"{type(exc).__name__}: {exc}"
        if len(detail) > 2000:
            detail = detail[:2000] + "...(truncated)"
        self.log(stage, "failed", detail)


@contextmanager
def event_logger(path: Path | None) -> Iterator[EventLogger]:
    yield EventLogger(path)
