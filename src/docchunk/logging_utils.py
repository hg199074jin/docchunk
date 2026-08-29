import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class EventLogger:
    """结构化 JSONL 事件日志；禁止写入文档全文。"""

    def __init__(self, path: Path | None) -> None:
        self.path = path

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


@contextmanager
def event_logger(path: Path | None) -> Iterator[EventLogger]:
    yield EventLogger(path)
