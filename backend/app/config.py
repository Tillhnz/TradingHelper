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


# Marktnachrichten für die Startseite: eine Quelle pro Zeile, "Name | Adresse" (RSS oder Atom).
DEFAULT_FEEDS = "\n".join([
    "tagesschau Wirtschaft | https://www.tagesschau.de/wirtschaft/index~rss2.xml",
    "tagesschau Finanzen | https://www.tagesschau.de/wirtschaft/finanzen/index~rss2.xml",
    "Handelsblatt Finanzen | https://www.handelsblatt.com/contentexport/feed/finanzen",
    "n-tv Wirtschaft | https://www.n-tv.de/wirtschaft/rss",
    "finanzen.net | https://www.finanzen.net/rss/news",
    "FAZ Finanzen | https://www.faz.net/rss/aktuell/finanzen/",
    "MarketWatch | https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "CNBC Markets | https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
])


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
    news_google: bool = field(default_factory=lambda: _bool(_env("news_google", "true")))
    news_yahoo: bool = field(default_factory=lambda: _bool(_env("news_yahoo", "true")))
    news_feeds: str = field(default_factory=lambda: _env("news_feeds", DEFAULT_FEEDS))
    app_url: str = field(default_factory=lambda: _env("app_url", ""))  # Adresse der Oberfläche für Push-Links
    ntfy_url: str = field(default_factory=lambda: _env("ntfy_url", "https://ntfy.sh"))
    ntfy_topic: str = field(default_factory=lambda: _env("ntfy_topic", ""))
    ntfy_token: str = field(default_factory=lambda: _env("ntfy_token", ""))
    report_enabled: bool = field(default_factory=lambda: _bool(_env("report_enabled", "true")))
    report_time: str = field(default_factory=lambda: _env("report_time", "07:00"))
    report_time_pm: str = field(default_factory=lambda: _env("report_time_pm", "16:00"))  # leer = kein Nachmittagsbericht
    report_weekends: bool = field(default_factory=lambda: _bool(_env("report_weekends", "false")))
    update_notify: bool = field(default_factory=lambda: _bool(_env("update_notify", "true")))
    alerts_enabled: bool = field(default_factory=lambda: _bool(_env("alerts_enabled", "true")))
    alert_interval_minutes: int = field(default_factory=lambda: int(_env("alert_interval_minutes", "5")))
    alert_start_hour: int = field(default_factory=lambda: int(_env("alert_start_hour", "8")))
    alert_end_hour: int = field(default_factory=lambda: int(_env("alert_end_hour", "22")))
    alert_weekends: bool = field(default_factory=lambda: _bool(_env("alert_weekends", "false")))
    alert_cooldown_minutes: int = field(default_factory=lambda: int(_env("alert_cooldown_minutes", "240")))
    display_currency: str = field(default_factory=lambda: _env("display_currency", "EUR"))  # oder "native"
    home_layout: str = ""  # Startseite: Reihenfolge, ausgeblendete Bausteine, Beträge verbergen (JSON, leer = Standard)
    invest_horizon: str = field(default_factory=lambda: _env("invest_horizon", "medium"))  # short|medium|long
    risk_profile: str = field(default_factory=lambda: _env("risk_profile", "balanced"))  # conservative|balanced|aggressive
    paper_enabled: bool = field(default_factory=lambda: _bool(_env("paper_enabled", "true")))
    paper_capital: int = field(default_factory=lambda: int(_env("paper_capital", "10000")))
    paper_fee: float = field(default_factory=lambda: float(_env("paper_fee", "1")))
    paper_time: str = field(default_factory=lambda: _env("paper_time", "17:45"))
    paper_notify: bool = field(default_factory=lambda: _bool(_env("paper_notify", "false")))
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
