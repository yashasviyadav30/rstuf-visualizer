# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Runtime configuration, read from environment variables.

Nothing is hardcoded, so a single container image serves any deployment.
Each setting is prefixed with ``RSTUF_``: the field ``metadata_url`` comes
from ``RSTUF_METADATA_URL``.
"""

import os
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

    Holds either the root metadata itself or a URL pointing at it. Left unset,
    the anchor is taken from the RSTUF API, and with neither available the
    service reports that it cannot verify anything rather than guessing.
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


def cors_origins() -> list[str]:
    """Origins allowed to call the API from a browser, comma separated.

    Empty by default, and that is the normal deployment: the interface is
    served from this same process, so a browser needs no cross-site
    permission to reach the API. A frontend development server does, because
    it answers on a port of its own.

    Read straight from the environment rather than through ``Settings``.
    Middleware is attached while the application is being built, and
    ``Settings`` requires a metadata URL that importing the application, or
    dumping its schema, has no reason to supply.
    """
    raw = os.environ.get("RSTUF_CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
