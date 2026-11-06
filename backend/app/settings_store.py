"""Einstellungen, die in der Oberfläche geändert werden.

Die Umgebungsvariablen liefern die Startwerte. Server-weite Einstellungen (Zeitplan, Nachrichtenquellen, Adresse …)
stehen in app_settings und dürfen nur vom Admin geändert werden. Persönliche Einstellungen (Strategie, Push-Kanal,
Anzeigewährung, Schattendepot) stehen je Nutzer in user_settings. Geheimnisse (API-Schlüssel, Token) werden nie an den
Browser zurückgegeben; dort steht nur, ob ein Wert gesetzt ist.
"""

from __future__ import annotations

import copy
import re
from zoneinfo import ZoneInfo

from .config import Settings
from .storage import Storage

# key -> (Typ, Gruppe, Geheimnis?)
FIELDS: dict[str, tuple[str, str, bool]] = {
    "invest_horizon": ("choice:short,medium,long", "strategy", False),
    "risk_profile": ("choice:conservative,balanced,aggressive", "strategy", False),
    "portfolio_size": ("int:0:1000000000", "strategy", False),
    "paper_enabled": ("bool", "paper", False),
    "paper_capital": ("int:100:10000000", "paper", False),
    "paper_fee": ("float:0:50", "paper", False),
    "paper_time": ("time", "paper", False),
    "paper_notify": ("bool", "paper", False),
    "ntfy_url": ("url", "notify", False),
    "ntfy_topic": ("topic", "notify", False),
    "ntfy_token": ("str:200", "notify", True),
    "finnhub_api_key": ("str:100", "news", True),
    "news_lookback_days": ("int:1:14", "news", False),
    "news_google": ("bool", "news", False),
    "news_yahoo": ("bool", "news", False),
    "news_feeds": ("feeds", "news", False),
    "report_enabled": ("bool", "schedule", False),
    "report_time": ("time", "schedule", False),
    "report_weekends": ("bool", "schedule", False),
    "alerts_enabled": ("bool", "schedule", False),
    "alert_interval_minutes": ("choice:1,2,5,10,15,30,60", "schedule", False),
    "alert_start_hour": ("int:0:23", "schedule", False),
    "alert_end_hour": ("int:0:23", "schedule", False),
    "alert_weekends": ("bool", "schedule", False),
    "alert_cooldown_minutes": ("int:0:10080", "schedule", False),
    "display_currency": ("choice:native,EUR,USD,CHF,GBP", "general", False),
    "timezone": ("tz", "general", False),
    "app_url": ("url_or_empty", "general", False),
}
# Diese Einstellungen hat jeder Nutzer für sich
USER_KEYS = {"invest_horizon", "risk_profile", "portfolio_size", "paper_enabled", "paper_capital", "paper_fee",
             "paper_notify", "ntfy_url", "ntfy_topic", "ntfy_token", "display_currency"}
SCHEDULE_KEYS = {k for k, v in FIELDS.items() if v[1] == "schedule"} | {"timezone", "paper_enabled", "paper_time"}


class SettingError(ValueError):
    pass


def coerce(key: str, raw):
    kind = FIELDS[key][0]
    base, *args = kind.split(":", 1)
    if base == "bool":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ("true", "1", "yes", "ja", "on"):
            return True
        if s in ("false", "0", "no", "nein", "off", ""):
            return False
        raise SettingError("Ja oder Nein erwartet")
    if base == "int":
        try:
            n = int(str(raw).strip())
        except ValueError as exc:
            raise SettingError("Ganze Zahl erwartet") from exc
        lo, hi = (int(x) for x in args[0].split(":"))
        if not lo <= n <= hi:
            raise SettingError(f"Wert zwischen {lo} und {hi} erwartet")
        return n
    if base == "float":
        try:
            x = float(str(raw).strip().replace(",", "."))
        except ValueError as exc:
            raise SettingError("Zahl erwartet") from exc
        lo, hi = (float(v) for v in args[0].split(":"))
        if not lo <= x <= hi or x != x:
            raise SettingError(f"Wert zwischen {lo:g} und {hi:g} erwartet")
        return round(x, 2)
    text = str(raw if raw is not None else "").strip()
    if base == "choice":
        options = args[0].split(",")
        if text not in options:
            raise SettingError(f"Erlaubt: {', '.join(options)}")
        return int(text) if text.isdigit() else text
    if base == "str":
        if len(text) > int(args[0]):
            raise SettingError("Zu lang")
        return text
    if base == "url_or_empty":
        if not text:
            return ""
        base = "url"
    if base == "url":
        if not re.match(r"^https?://[^\s]+$", text) or len(text) > 300:
            raise SettingError("Adresse mit http:// oder https:// erwartet")
        return text.rstrip("/")
    if base == "topic":
        if text and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", text):
            raise SettingError("Nur Buchstaben, Ziffern, - und _ (höchstens 64 Zeichen)")
        return text
    if base == "time":
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise SettingError("Uhrzeit im Format HH:MM erwartet")
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    if base == "feeds":
        lines = [ln.strip() for ln in str(raw if raw is not None else "").splitlines() if ln.strip()]
        if len(lines) > 30:
            raise SettingError("Höchstens 30 Quellen")
        out = []
        for ln in lines:
            if ln.startswith("#"):  # ausgeschaltete Quelle
                out.append(ln[:480])
                continue
            name, _, url = ln.rpartition("|") if "|" in ln else ("", "", ln)
            name, url = name.strip(), url.strip()
            if not re.match(r"^https?://[^\s|]+$", url) or len(url) > 400 or len(name) > 60:
                raise SettingError(f"Ungültige Zeile: {ln[:60]} (Format: Name | https://…)")
            out.append(f"{name} | {url}" if name else url)
        return "\n".join(out)
    if base == "tz":
        try:
            ZoneInfo(text)
        except Exception as exc:  # noqa: BLE001
            raise SettingError("Unbekannte Zeitzone (z. B. Europe/Berlin)") from exc
        return text
    raise SettingError("Unbekanntes Feld")


def _serialize(value) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def apply_overrides(storage: Storage, settings: Settings) -> None:
    """Server-weite Werte übernehmen. Persönliche Werte aus älteren Versionen (damals global) gehen an den Besitzer."""
    saved = storage.app_settings()
    owner = storage.admin()
    for key in [k for k in saved if k in USER_KEYS]:
        if owner:
            mine = storage.for_user(owner["id"])
            if key not in mine.user_settings():
                mine.set_user_setting(key, saved[key])
            storage.delete_app_setting(key)
    for key, value in saved.items():
        if key in FIELDS and key not in USER_KEYS:
            try:
                setattr(settings, key, coerce(key, value))
            except SettingError:
                continue


def for_user(storage: Storage, base: Settings) -> Settings:
    """Einstellungen eines Nutzers: server-weite Werte plus seine persönlichen."""
    cfg = copy.copy(base)
    for key, value in storage.user_settings().items():
        if key in USER_KEYS:
            try:
                setattr(cfg, key, coerce(key, value))
            except SettingError:
                continue
    return cfg


def save(storage: Storage, settings: Settings, values: dict, base: Settings | None = None,
         is_admin: bool = True) -> list[str]:
    """Speichert Änderungen. Geheimnisse: None = behalten, "" = löschen. Gibt geänderte Schlüssel zurück.
    settings: die Einstellungen des Nutzers; base: die server-weiten (Standard: dieselben)."""
    base = base or settings
    clean, errors = {}, {}
    for key, raw in values.items():
        if key not in FIELDS:
            errors[key] = "Unbekannte Einstellung"
            continue
        if key not in USER_KEYS and not is_admin:
            errors[key] = "Nur der Admin kann das ändern"
            continue
        if FIELDS[key][2] and raw is None:
            continue
        try:
            clean[key] = coerce(key, raw)
        except SettingError as e:
            errors[key] = str(e)
    if errors:
        raise SettingError("; ".join(f"{k}: {v}" for k, v in errors.items()))
    for key, value in clean.items():
        if key in USER_KEYS:
            storage.set_user_setting(key, _serialize(value))
        else:
            storage.set_app_setting(key, _serialize(value))
            setattr(base, key, value)
        setattr(settings, key, value)
    return list(clean)


def describe(storage: Storage, settings: Settings, is_admin: bool = True) -> dict:
    saved = {**storage.app_settings(), **storage.user_settings()}
    out = {}
    for key, (kind, group, secret) in FIELDS.items():
        if key not in USER_KEYS and not is_admin:
            continue
        value = getattr(settings, key)
        entry = {"group": group, "secret": secret, "from_ui": key in saved, "type": kind,
                 "scope": "user" if key in USER_KEYS else "server"}
        if secret:
            entry["set"] = bool(str(value).strip())
        else:
            entry["value"] = value
        out[key] = entry
    return out
