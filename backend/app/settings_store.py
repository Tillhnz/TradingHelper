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
    "report_time_pm": ("time_or_empty", "schedule", False),
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
    "update_notify": ("bool", "general", False),
    "home_layout": ("home_layout", "home", False),
    "require_2fa": ("bool", "security", False),
    "trusted_device_days": ("int:1:365", "security", False),
    "fints_product_id": ("str:40", "brokers", True),
    "broker_sync_hours": ("int:0:168", "brokers", False),
    "social_enabled": ("bool", "data", False),
    "reddit_client_id": ("str:100", "data", True),
    "reddit_client_secret": ("str:200", "data", True),
    "bluesky_handle": ("str:100", "data", False),
    "bluesky_app_password": ("str:100", "data", True),
    "fred_api_key": ("str:100", "data", True),
    "model_enabled": ("bool", "model", False),
    "model_time": ("time", "model", False),
    "model_weight_max": ("float:0:1", "model", False),
}
# Bausteine der Startseite (frei anordnen, Größe wählen; „chart“ darf mehrfach vorkommen)
HOME_TYPES = ["greeting", "portfolio", "allocation", "today", "watchlist", "movers", "markets", "macro", "mood",
              "model", "review", "news", "market_news", "alerts", "shadow", "setup", "chart"]
HOME_SIZES = ["s", "m", "l", "xl"]
HOME_DEFAULT = [("setup", "xl"), ("greeting", "xl"), ("portfolio", "l"), ("markets", "s"), ("today", "l"),
                ("mood", "s"), ("watchlist", "xl"), ("model", "m"), ("macro", "m"), ("news", "m"),
                ("market_news", "m"), ("review", "m"), ("alerts", "m")]
HOME_WIDGETS = ["setup", "tiles", "important", "assets", "news", "alerts"]  # altes Format (bis 0.20)
_OLD_TO_NEW = {"setup": ("setup", "xl"), "tiles": ("portfolio", "l"), "important": ("today", "xl"),
               "assets": ("watchlist", "xl"), "news": ("news", "m"), "alerts": ("alerts", "m")}
# Diese Einstellungen hat jeder Nutzer für sich
USER_KEYS = {"invest_horizon", "risk_profile", "portfolio_size", "paper_enabled", "paper_capital", "paper_fee",
             "paper_notify", "ntfy_url", "ntfy_topic", "ntfy_token", "display_currency", "home_layout"}
SCHEDULE_KEYS = {k for k, v in FIELDS.items() if v[1] == "schedule"} | {"timezone", "model_time", "model_enabled",
                                                                     "broker_sync_hours"}


class SettingError(ValueError):
    pass


def _home_layout(raw) -> str:
    """{"v": 2, "widgets": [{"id", "type", "size", "config"}], "private": bool}. Das alte Format (order/hidden)
    wird umgewandelt; unbekannte Bausteine fliegen raus."""
    import json

    if raw in (None, ""):
        return ""
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (ValueError, TypeError) as exc:
        raise SettingError("Ungültiges Startseiten-Layout") from exc
    if not isinstance(data, dict):
        raise SettingError("Ungültiges Startseiten-Layout")
    if "widgets" not in data and "order" in data:  # altes Format
        hidden = set(data.get("hidden") or [])
        widgets = [{"id": f"w{i}", "type": _OLD_TO_NEW[w][0], "size": _OLD_TO_NEW[w][1]}
                   for i, w in enumerate(data.get("order") or []) if w in _OLD_TO_NEW and w not in hidden]
    else:
        widgets = data.get("widgets") or []
    if not isinstance(widgets, list) or len(widgets) > 40:
        raise SettingError("Höchstens 40 Bausteine")
    out, ids, types = [], set(), set()
    for i, w in enumerate(widgets):
        if not isinstance(w, dict) or w.get("type") not in HOME_TYPES:
            continue
        t = w["type"]
        if t != "chart" and t in types:
            continue  # jeden Baustein (außer Mini-Chart) nur einmal
        wid = str(w.get("id") or f"w{i}")[:24]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", wid) or wid in ids:
            wid = f"w{i}x{len(ids)}"
        cfg = {}
        if t == "chart":
            sym = str((w.get("config") or {}).get("symbol") or "").strip().upper()
            if not re.fullmatch(r"[A-Z0-9^=.\-]{1,30}", sym):
                continue
            cfg["symbol"] = sym
            period = (w.get("config") or {}).get("period")
            if period in ("1mo", "3mo", "6mo", "1y", "5y"):
                cfg["period"] = period
        size = w.get("size") if w.get("size") in HOME_SIZES else "m"
        out.append({"id": wid, "type": t, "size": size, **({"config": cfg} if cfg else {})})
        ids.add(wid)
        types.add(t)
    return json.dumps({"v": 2, "widgets": out, "private": bool(data.get("private"))}, separators=(",", ":"))


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
    if base == "time_or_empty":
        if not str(raw if raw is not None else "").strip():
            return ""
        base = "time"
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
    if base == "home_layout":
        return _home_layout(raw)
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
