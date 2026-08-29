from pathlib import Path

from pydantic import BaseModel


class SourceRef(BaseModel):
    path: str
    sha256: str
    media_type: str
    size_bytes: int

    @classmethod
    def from_path(cls, path: Path, sha256: str, media_type: str) -> "SourceRef":
        return cls(
            path=str(path),
            sha256=sha256,
            media_type=media_type,
            size_bytes=path.stat().st_size,
        )
