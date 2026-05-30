from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openalex_email: str = ""
    openalex_api_key: str = ""
    openalex_base_url: str = "https://api.openalex.org"

    worldbank_base_url: str = "https://api.worldbank.org/v2"
    hipolabs_base_url: str = "http://universities.hipolabs.com"

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "papers"
    mysql_password: str = "paperspass"
    mysql_database: str = "papers"
    database_url: str = ""

    http_timeout: float = 30.0
    http_max_retries: int = 5
    http_backoff_base: float = 1.0

    log_level: str = "INFO"
    log_dir: str = "logs"
    target_gb: float = 5.0

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        pwd = quote_plus(self.mysql_password)
        user = quote_plus(self.mysql_user)
        return (
            f"mysql+pymysql://{user}:{pwd}@{self.mysql_host}:{self.mysql_port}"
            f"/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def safe_sqlalchemy_url(self) -> str:
        url = self.sqlalchemy_url
        if self.database_url or not self.mysql_password:
            return url
        return url.replace(quote_plus(self.mysql_password), "***", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
