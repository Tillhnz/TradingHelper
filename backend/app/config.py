"""Einstellungen des laufenden Prozesses.

Die Umgebungsvariablen (.env, Präfix TH_) liefern nur Startwerte. Alles, was in der Oberfläche unter
Einstellungen gespeichert wird, liegt in der Datenbank und überschreibt diese Werte (siehe settings_store.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(f"TH_{name.upper()}", os.environ.get(name.upper(), default))


def _bool(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "ja", "on")


@dataclass
class Settings:
    # Nur über die Umgebung (Infrastruktur)
    secret_key: str = field(default_factory=lambda: _env("secret_key", "dev-secret-change-me"))
    data_dir: Path = field(default_factory=lambda: Path(_env("data_dir", "./data")))
    updater_url: str = field(default_factory=lambda: _env("updater_url", ""))
    scheduler_enabled: bool = field(default_factory=lambda: _bool(_env("scheduler_enabled", "true")))

    # In der Oberfläche änderbar
    timezone: str = field(default_factory=lambda: _env("timezone", "Europe/Berlin"))
    finnhub_api_key: str = field(default_factory=lambda: _env("finnhub_api_key", ""))
    news_lookback_days: int = field(default_factory=lambda: int(_env("news_lookback_days", "3")))
    ntfy_url: str = field(default_factory=lambda: _env("ntfy_url", "https://ntfy.sh"))
    ntfy_topic: str = field(default_factory=lambda: _env("ntfy_topic", ""))
    ntfy_token: str = field(default_factory=lambda: _env("ntfy_token", ""))
    report_enabled: bool = field(default_factory=lambda: _bool(_env("report_enabled", "true")))
    report_time: str = field(default_factory=lambda: _env("report_time", "07:30"))
    report_weekends: bool = field(default_factory=lambda: _bool(_env("report_weekends", "false")))
    alerts_enabled: bool = field(default_factory=lambda: _bool(_env("alerts_enabled", "true")))
    alert_interval_minutes: int = field(default_factory=lambda: int(_env("alert_interval_minutes", "5")))
    alert_start_hour: int = field(default_factory=lambda: int(_env("alert_start_hour", "8")))
    alert_end_hour: int = field(default_factory=lambda: int(_env("alert_end_hour", "22")))
    alert_weekends: bool = field(default_factory=lambda: _bool(_env("alert_weekends", "false")))
    alert_cooldown_minutes: int = field(default_factory=lambda: int(_env("alert_cooldown_minutes", "240")))
    display_currency: str = field(default_factory=lambda: _env("display_currency", "EUR"))  # oder "native"
    invest_horizon: str = field(default_factory=lambda: _env("invest_horizon", "medium"))  # short|medium|long
    risk_profile: str = field(default_factory=lambda: _env("risk_profile", "balanced"))  # conservative|balanced|aggressive
    portfolio_size: int = field(default_factory=lambda: int(_env("portfolio_size", "0")))  # 0 = aus

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "tradehelper.db"

    def reset(self) -> None:
        """Alle Werte wieder aus der Umgebung lesen (für Tests)."""
        fresh = Settings()
        for f in fields(self):
            setattr(self, f.name, getattr(fresh, f.name))


settings = Settings()


def get_settings() -> Settings:
    return settings
