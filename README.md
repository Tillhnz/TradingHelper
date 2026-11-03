# TradeHelper

Selbst gehosteter Trading-Assistent für Proxmox: Watchlist, Chartanalyse mit bekannten Indikatoren, Alarme wie bei TradingView und jeden Morgen eine Einschätzung per Push aufs Handy. Bedienung, Einstellungen und Updates laufen komplett über die Weboberfläche.

> ⚠️ Die Einschätzungen sind regelbasiert und automatisch erzeugt. Sie sind **keine Anlageberatung**.

## Installation auf Proxmox (ein Befehl)

In der Shell des **Proxmox-Hosts** (als root):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Tillhnz/tradinghelper/main/proxmox/tradehelper-lxc.sh)"
```

Das Skript legt einen Debian-12-Container mit Docker an, installiert TradeHelper darin und zeigt am Ende die Adresse, z. B. `http://192.168.178.51:8080`. Dort legst du beim ersten Aufruf dein Konto an.

Anpassen lässt sich der Container über Variablen vor dem Befehl, z. B. feste IP:

```bash
CT_IP=192.168.178.51/24 CT_GW=192.168.178.1 bash -c "$(curl -fsSL https://raw.githubusercontent.com/Tillhnz/tradinghelper/main/proxmox/tradehelper-lxc.sh)"
```

Alle Optionen stehen oben in [`proxmox/tradehelper-lxc.sh`](proxmox/tradehelper-lxc.sh).

**Ohne Proxmox** (Debian/Ubuntu-Server, VM oder vorhandener LXC mit Nesting):

```bash
curl -fsSL https://raw.githubusercontent.com/Tillhnz/tradinghelper/main/install.sh | bash
```

## Erste Schritte in der Oberfläche

1. **Konto anlegen** – beim ersten Aufruf.
2. **Einstellungen → Benachrichtigungen:** [ntfy](https://ntfy.sh)-App installieren, ein Topic mit zufälligem Namen abonnieren, denselben Namen eintragen, „Testnachricht senden“.
3. **Einstellungen → Nachrichten:** kostenlosen Schlüssel von [finnhub.io](https://finnhub.io/register) eintragen (optional, sonst ohne News).
4. **Watchlist** füllen. Ab dem nächsten Morgen (Standard Mo–Fr 07:30) kommt der Report.
5. **Alarme** anlegen.

## Funktionen

| Bereich | Details |
|---|---|
| Heute | Einschätzung je Watchlist-Wert: 🟢 Kaufen prüfen · 🟡 Halten · 🔴 Reduzieren prüfen, mit Begründung und Schlagzeile; per Knopf als Push senden |
| Watchlist | Kurs, Tagesänderung, 30-Tage-Verlauf, RSI, Einschätzung |
| Chart | Kerzen mit Volumen, SMA 20/50/200, Bollinger, Unterstützung/Widerstand, RSI- und MACD-Fenster; Tag, Woche, Stunde, 15 Minuten |
| Analyse | SMA, EMA, RSI, MACD, Bollinger, Stochastik, ADX, ATR, OBV, Volumen → Einzelsignale und Score; News-Stimmung aus Finnhub-Schlagzeilen (Gewicht einstellbar) |
| Alarme | 16 Bedingungen: Kurs über/unter, Kreuzungen, RSI-Schwellen, MACD-Kreuz, Golden/Death Cross, Kurs kreuzt MA, Bollinger-Ausbruch, Volumenspitze, neue Hochs/Tiefs, Tagesbewegung; beliebiges Kerzenintervall, Pause nach Auslösung, einmalig |
| Einstellungen | ntfy, Finnhub, Zeitplan von Report und Alarmprüfung, Zeitzone – alles ohne Neustart |
| Administration | Zustand der Dienste, **Update per Knopf** (mit Sicherung vorher und automatischem Zurückrollen), Sicherungen |

Symbole in Yahoo-Schreibweise: `AAPL`, `SAP.DE` (Xetra), `^GDAXI` (DAX), `BTC-EUR`, `EURUSD=X`, `IWDA.AS`.

## Updates

In der Oberfläche unter **Administration → Nach Updates suchen → Jetzt aktualisieren**. Ein Hinweis „Update verfügbar“ erscheint auch in der Seitenleiste. Vor jedem Update wird die Datenbank gesichert; startet die neue Version nicht, läuft wieder die alte.

Im Terminal geht es auch:

```bash
pct enter <ID>                    # vom Proxmox-Host in den Container
cd ~/tradinghelper && ./install.sh update
```

## Befehle im Container

```bash
cd ~/tradinghelper
./install.sh update        # neueste Version
./install.sh backup        # Sicherung nach backups/
./install.sh restore backups/tradehelper-….db.gz
./install.sh reset-login   # Passwort vergessen: Konto neu anlegen (Daten bleiben)
./install.sh logs
```

## Aufbau

```
backend/    FastAPI, Analyse, Alarme, Scheduler, SQLite (data/tradehelper.db)
frontend/   React + Vite, Charts mit lightweight-charts, ausgeliefert von nginx
updater/    kleiner Dienst für den Update-Knopf (git pull, neu bauen, zurückrollen)
proxmox/    Skript für den Proxmox-Host
install.sh  Installation und Wartung
```

Die API ist unter `/api/docs` dokumentiert (Anmeldung über `/api/auth/login`, Token als `Authorization: Bearer …`).

## Wie die Einschätzung entsteht

Die **Anlagestrategie** (Einstellungen) steuert alles:

| Horizont | Was zählt | News | Stopp | Ziel |
|---|---|---|---|---|
| Kurzfristig | RSI, MACD, Stochastik, Bollinger, EMA 9/21, Volumen (×1,5); Trend nur ×0,5 | 40 % | 1,5 × ATR | nächster Widerstand |
| Mittelfristig | alles gleich gewichtet | 30 % | 2,5 × ATR | nächster Widerstand |
| Langfristig | Trend ×2, Golden/Death Cross, 6-/12-Monats-Momentum, Rücksetzer im Aufwärtstrend; Oszillatoren kaum | 15 % | 3,5 × ATR | – |

| Risiko | Kaufen ab | Reduzieren ab | Trendfilter | Chance/Risiko | Schwankung | Position |
|---|---|---|---|---|---|---|
| Konservativ | +0,45 | −0,25 | nie unter SMA200 | ≥ 2 | Abschlag ab 4 %/Tag | 0,5 % Risiko, max. 5 % |
| Ausgewogen | +0,35 | −0,35 | unter SMA200 nur mit Bestätigung | ≥ 1,5 | Abschlag ab 6 %/Tag | 1 % Risiko, max. 10 % |
| Offensiv | +0,25 | −0,45 | keiner | ≥ 1 | – | 2 % Risiko, max. 20 % |

Jeder Indikator liefert ein Signal zwischen −2 und +2, gewichtet nach Horizont und auf −1…+1 normiert, dann mit der News-Stimmung gemischt. Mit hinterlegter Depotgröße schlägt TradeHelper eine Positionsgröße vor (Stückzahl so, dass ein Stopp höchstens das Depotrisiko kostet). Die Logik steht in `backend/app/analysis.py`.

## Entwicklung

```bash
cd backend && pip install -r requirements-dev.txt && pytest
uvicorn app.main:app --reload              # Backend auf :8000
cd frontend && npm install && npm run dev  # Oberfläche auf :5173
```

## Grenzen

- Kurse über yfinance (inoffizielle Yahoo-Schnittstelle): Ausfälle oder Verzögerungen sind möglich, Intraday-Daten nur für begrenzte Zeiträume.
- Finnhub-News decken vor allem US-Werte ab.
- Die News-Stimmung ist ein einfaches Wortlisten-Verfahren.

Lizenz: MIT
