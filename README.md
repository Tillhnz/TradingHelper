# TradeHelper

Selbst gehosteter Trading-Assistent für Proxmox: Kurse per API, Chartanalyse mit bekannten Indikatoren, TradingView-ähnliche Alarme und ein Morgenreport mit Handlungsempfehlungen für deine Watchlist – alles über den Befehl `tradehelper`.

> ⚠️ Die Empfehlungen sind regelbasiert und automatisch erzeugt. Sie sind **keine Anlageberatung**.

## Funktionen

| Bereich | Details |
|---|---|
| Kurse | yfinance (kein Key), Yahoo-Notation: `AAPL`, `SAP.DE`, `^GDAXI`, `BTC-USD`, `EURUSD=X` |
| News | Finnhub Company News (Gratis-Key) mit regelbasiertem Sentiment (DE/EN-Lexikon) |
| Indikatoren | SMA 20/50/200, EMA 9/21, RSI, MACD, Bollinger, Stochastik, ADX/DI, ATR, OBV, Volumen, Unterstützung/Widerstand |
| Analyse | Einzelsignale (−2…+2) → normierter Score; 70 % Technik + 30 % News → 🟢 Kaufen prüfen / 🟡 Halten / 🔴 Reduzieren prüfen |
| Alarme | 16 Typen (Kurs, Crossings, RSI, MACD, MA-Cross, Bollinger-Ausbruch, Volumen, neue Hochs/Tiefs), beliebiges Intervall, Cooldown, einmalig oder dauerhaft |
| Benachrichtigung | ntfy (ntfy.sh oder selbst gehostet) |
| Morgenreport | Mo–Fr um 07:30 (konfigurierbar) per ntfy |
| Web | REST-API mit Swagger unter `/docs`, interaktiver Chart unter `/chart/{SYMBOL}` (Candles, SMA, Bollinger, RSI, MACD) |

## Installation auf Proxmox

### Variante A: LXC-Container mit systemd (empfohlen)

1. In Proxmox einen Debian-12- oder Ubuntu-24.04-LXC anlegen (1 vCPU, 512 MB RAM, 4 GB Disk reichen).
2. In der Konsole des Containers als root:
   ```bash
   apt update && apt install -y curl
   bash <(curl -fsSL https://raw.githubusercontent.com/Tillhnz/tradinghelper/main/deploy/install.sh)
   ```
3. `.env` anpassen und neu starten:
   ```bash
   nano /opt/tradehelper/.env
   systemctl restart tradehelper
   ```

Update später: Installationsskript erneut ausführen (macht `git pull` + Neuinstallation) und `systemctl restart tradehelper`.

### Variante B: Docker

```bash
git clone https://github.com/Tillhnz/tradinghelper.git && cd tradinghelper
cp .env.example .env && nano .env
docker compose up -d --build
# Befehle im Container:
docker compose exec tradehelper tradehelper watchlist add AAPL
```

Eigener ntfy-Server dazu: `docker compose --profile ntfy up -d` und `TH_NTFY_URL=http://ntfy:80`.

## Konfiguration (`.env`)

| Variable | Default | Bedeutung |
|---|---|---|
| `TH_FINNHUB_API_KEY` | – | Key von [finnhub.io](https://finnhub.io/register) für News |
| `TH_NTFY_URL` | `https://ntfy.sh` | ntfy-Server |
| `TH_NTFY_TOPIC` | – | Topic, das du in der ntfy-App abonnierst (bei ntfy.sh zufällig wählen!) |
| `TH_NTFY_TOKEN` | – | Optionaler Access-Token |
| `TH_API_KEY` | – | Wenn gesetzt, braucht jeder API-Call den Header `X-API-Key` (Chart: `?key=…`) |
| `TH_REPORT_TIME` | `07:30` | Uhrzeit des Morgenreports (Mo–Fr) |
| `TH_ALERT_INTERVAL_MINUTES` | `5` | Prüfintervall der Alarme |
| `TH_ALERT_HOURS` | `8-22` | Stunden, in denen geprüft wird |
| `TH_ALERT_COOLDOWN_MINUTES` | `240` | Mindestabstand zwischen zwei Auslösungen desselben Alarms |

## Befehle

```bash
tradehelper quote AAPL SAP.DE ^GDAXI          # Kurse
tradehelper analyze NVDA                       # Chartanalyse + Einschätzung
tradehelper analyze BTC-USD --interval 1h --period 1mo
tradehelper news AAPL                          # Nachrichten mit Sentiment

tradehelper watchlist add AAPL MSFT SAP.DE
tradehelper watchlist list
tradehelper report                             # Morgenreport jetzt anzeigen
tradehelper report --send                      # ... und per ntfy senden

tradehelper alert kinds                        # alle Alarmtypen
tradehelper alert add AAPL price_above -v 250
tradehelper alert add AAPL rsi_below -v 30
tradehelper alert add SAP.DE ma_cross_up -p fast=50 -p slow=200      # Golden Cross
tradehelper alert add BTC-USD bb_break --interval 1h
tradehelper alert add TSLA pct_change -v 5 --once
tradehelper alert list
tradehelper alert check --dry-run              # sofort prüfen, ohne zu senden
tradehelper alert log

tradehelper notify-test                        # ntfy testen
tradehelper serve                              # API + Scheduler (läuft als Dienst)
```

## Alarmtypen

| Typ | Parameter | Auslösung |
|---|---|---|
| `price_above` / `price_below` | `value` | Kurs über/unter Wert (wiederholt nach Cooldown) |
| `cross_up` / `cross_down` | `value` | Kurs kreuzt Wert |
| `pct_change` | `value=5` | Bewegung ggü. Vorkerze ≥ ±X % |
| `rsi_above` / `rsi_below` | `value`, `period=14` | RSI kreuzt Schwelle |
| `macd_cross_up` / `macd_cross_down` | – | MACD kreuzt Signallinie |
| `ma_cross_up` / `ma_cross_down` | `fast=50`, `slow=200`, `type=sma\|ema` | MA-Crossover (Golden/Death Cross) |
| `price_cross_ma` | `period=200`, `type=sma` | Kurs kreuzt MA |
| `bb_break` | `period=20`, `k=2` | Ausbruch aus Bollinger-Bändern |
| `volume_spike` | `factor=2` | Volumen ≥ Faktor × 20er-Schnitt |
| `new_high` / `new_low` | `lookback=52` | Neues N-Perioden-Hoch/-Tief |

Crossing-Alarme vergleichen die letzten beiden Kerzen – wie `ta.crossover` in TradingView. Bei Tageskerzen wird die laufende Tageskerze verwendet, ein Signal kann also intraday auslösen.

## REST-API

Swagger-Doku: `http://<host>:8080/docs`

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/quote/{symbol}` | Aktueller Kurs |
| GET | `/history/{symbol}?period=1y&interval=1d` | OHLCV + Indikatoren |
| GET | `/analysis/{symbol}` | Analyse, Signale, Einschätzung, News |
| GET | `/news/{symbol}` | News mit Sentiment |
| GET/POST/DELETE | `/watchlist` | Watchlist verwalten |
| GET/POST/DELETE | `/alerts` | Alarme verwalten (`GET /alerts/kinds` für Typen) |
| POST | `/alerts/check` | Alarme sofort prüfen |
| GET | `/report` | Morgenreport als JSON |
| GET | `/chart/{symbol}` | Interaktiver Chart im Browser |

Beispiel:
```bash
curl -X POST localhost:8080/alerts -H 'Content-Type: application/json' \
  -d '{"symbol":"AAPL","kind":"rsi_below","params":{"value":30}}'
```

## Wie die Empfehlung entsteht

Jeder Indikator liefert ein Signal zwischen −2 und +2 (Trend über SMA200, Golden/Death Cross, RSI-Zone, MACD-Kreuzung bzw. -Lage, Bollinger-Übertreibung, Stochastik-Wende, ADX-Trendstärke, Volumenbestätigung). Die Summe wird auf −1…+1 normiert und mit dem News-Sentiment der letzten Tage gewichtet (70/30). Ab +0,35 lautet die Einschätzung „Kaufen prüfen“, ab −0,35 „Reduzieren prüfen“, dazwischen „Halten / beobachten“. Die Logik steht in `src/tradehelper/analysis.py` und lässt sich leicht anpassen.

## Entwicklung

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Grenzen

- yfinance nutzt inoffizielle Yahoo-Endpunkte; Ausfälle oder Rate-Limits sind möglich, Kurse können verzögert sein.
- Finnhub-Company-News deckt vor allem US-Werte ab; für deutsche Werte (`SAP.DE`) wird das Basissymbol gesucht, das nicht immer Treffer liefert.
- Das Sentiment ist ein einfaches Lexikon-Verfahren und erkennt keine Ironie oder Zusammenhänge.

Lizenz: MIT
