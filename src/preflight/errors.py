class PreflightError(Exception):
    """Base error for expected preflight failures."""


class ConfigError(PreflightError):
    """Raised when repository preflight configuration is invalid."""


class GitError(PreflightError):
    """Raised when Git state or Git commands cannot be inspected safely."""


class GitTimeoutError(GitError):
    """Raised when a Git subprocess exceeds its operation timeout."""
