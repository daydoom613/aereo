"""Runtime settings, read from environment variables prefixed with APP_ (or a .env file)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MEBIBYTE = 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/measurements.db"
    # Largest request body accepted by the upload endpoint.
    max_upload_bytes: int = Field(default=50 * MEBIBYTE, gt=0)
    # Zip-bomb guards: the most a shapefile archive may declare when uncompressed, and its entries.
    max_archive_uncompressed_bytes: int = Field(default=500 * MEBIBYTE, gt=0)
    max_archive_entries: int = Field(default=1000, gt=0)
    log_level: str = "INFO"
