from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    smtp_host: str = "0.0.0.0"
    smtp_port: int = 2525
    smtp_auth_user: str = ""
    smtp_auth_password: str = ""
    mail_domain: str = "localhost"

    outbound_mode: Literal["relay", "direct"] = "direct"
    outbound_smtp_host: str = ""
    outbound_smtp_port: int = 587
    outbound_smtp_use_tls: bool = True
    outbound_smtp_user: str = ""
    outbound_smtp_password: str = ""
    outbound_from_email: str = ""

    http_host: str = "0.0.0.0"
    port: int = Field(default=8000, alias="PORT")

    api_key: str = ""
    data_dir: Path = Path("data")

    @field_validator("data_dir", mode="before")
    @classmethod
    def _coerce_data_dir(cls, value: str | Path) -> Path:
        return Path(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
