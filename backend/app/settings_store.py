"""Einstellungen, die in der Oberfläche geändert werden.

Die Umgebungsvariablen liefern die Startwerte. Was gespeichert wird, steht in der Tabelle app_settings und
überschreibt sie. Geheimnisse (API-Schlüssel, Token) werden nie an den Browser zurückgegeben; dort steht nur,
ob ein Wert gesetzt ist.
"""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from .config import Settings
from .storage import Storage

# key -> (Typ, Gruppe, Geheimnis?)
FIELDS: dict[str, tuple[str, str, bool]] = {
    "ntfy_url": ("url", "notify", False),
    "ntfy_topic": ("topic", "notify", False),
    "ntfy_token": ("str:200", "notify", True),
    "finnhub_api_key": ("str:100", "news", True),
    "news_lookback_days": ("int:1:14", "news", False),
    "news_weight": ("int:0:100", "news", False),
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
    "history_period": ("choice:6mo,1y,2y,5y", "general", False),
}
SCHEDULE_KEYS = {k for k, v in FIELDS.items() if v[1] == "schedule"} | {"timezone"}


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
    for key, value in storage.app_settings().items():
        if key in FIELDS:
            try:
                setattr(settings, key, coerce(key, value))
            except SettingError:
                continue


def save(storage: Storage, settings: Settings, values: dict) -> list[str]:
    """Speichert Änderungen. Geheimnisse: None = behalten, "" = löschen. Gibt geänderte Schlüssel zurück."""
    clean, errors = {}, {}
    for key, raw in values.items():
        if key not in FIELDS:
            errors[key] = "Unbekannte Einstellung"
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
        storage.set_app_setting(key, _serialize(value))
        setattr(settings, key, value)
    return list(clean)


def describe(storage: Storage, settings: Settings) -> dict:
    saved = storage.app_settings()
    out = {}
    for key, (kind, group, secret) in FIELDS.items():
        value = getattr(settings, key)
        entry = {"group": group, "secret": secret, "from_ui": key in saved, "type": kind}
        if secret:
            entry["set"] = bool(str(value).strip())
        else:
            entry["value"] = value
        out[key] = entry
    return out
