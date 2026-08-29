class DocchunkError(Exception):
    """Base error for docchunk."""


class ExternalToolError(DocchunkError):
    """Raised when MinerU or Pandoc fails."""


class VerificationError(DocchunkError):
    """Raised when a generated corpus fails integrity checks."""


class UnsupportedInputError(DocchunkError):
    """Raised when no adapter supports an input."""


class RebuildError(DocchunkError):
    """Raised when rebuild-batches fails verification."""
