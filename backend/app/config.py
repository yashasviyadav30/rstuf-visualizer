"""Runtime configuration, read from environment variables.

Nothing is hardcoded, so a single container image serves any deployment.
Each setting is prefixed with ``RSTUF_``: the field ``metadata_url`` comes
from ``RSTUF_METADATA_URL``.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings validated once at startup.

    A missing or malformed required value stops the application immediately,
    which is preferable to failing later with an unclear error.
    """

    model_config = SettingsConfigDict(env_prefix="RSTUF_")

    metadata_url: str
    """Base URL of the signed TUF metadata. Required."""

    trusted_root: str | None = None
    """Base64 trust anchor, following the RSTUF client convention.

    Left unset, the client falls back to its cached root, which is not
    recommended outside local development.
    """

    api_url: str | None = None
    """Base URL of the RSTUF API. Unset hides the repository status panel."""

    cache_ttl_seconds: int = 30
    """How long a built response stays reusable."""

    request_timeout_seconds: float = 10.0
    """Ceiling on any single upstream request."""


@lru_cache
def get_settings() -> Settings:
    """Return the settings, reading the environment only on first call."""
    return Settings()
