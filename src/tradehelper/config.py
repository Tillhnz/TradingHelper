"""Konfiguration über Umgebungsvariablen bzw. .env-Datei (Präfix TH_)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TH_", env_file=".env", extra="ignore")

    # Speicherort für SQLite-Datenbank
    data_dir: Path = Path("./data")

    # Finnhub (News). Gratis-Key: https://finnhub.io
    finnhub_api_key: str = ""
    news_lookback_days: int = 3

    # ntfy (Benachrichtigungen)
    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""  # optional, für geschützte Topics

    # API-Server
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_key: str = ""  # wenn gesetzt, muss jeder Request X-API-Key mitsenden

    # Zeitplan
    timezone: str = "Europe/Berlin"
    report_time: str = "07:30"  # HH:MM, Mo–Fr
    alert_interval_minutes: int = 5
    alert_hours: str = "8-22"  # Stunden, in denen Alarme geprüft werden (Mo–Fr)
    alert_cooldown_minutes: int = 240

    # Analyse
    history_period: str = "1y"
    history_interval: str = "1d"

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "tradehelper.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
