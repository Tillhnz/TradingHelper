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
3. **Einstellungen → Nachrichten:** Quellen wählen. Google News und Yahoo Finance laufen ohne Schlüssel; ein kostenloser Schlüssel von [finnhub.io](https://finnhub.io/register) ist optional. Die Marktnachrichten auf der Startseite kommen aus einer frei editierbaren RSS-Liste (tagesschau, Handelsblatt, n-tv, finanzen.net, FAZ, MarketWatch, CNBC).
4. **Watchlist** füllen. Ab dem nächsten Morgen (Standard Mo–Fr 07:30) kommt der Report.
5. **Alarme** anlegen.

## Funktionen

| Bereich | Details |
|---|---|
| Heute | Einschätzung je Watchlist-Wert: 🟢 Kaufen prüfen · 🟡 Halten · 🔴 Reduzieren prüfen, mit Begründung und Schlagzeile. Der Morgenbericht kommt als kurze Push-Nachricht; Antippen öffnet ihn vollständig als Fenster auf der Webseite |
| Charts | Eigener Arbeitsplatz je Wert: waagrechte Linien (mit Alarm per Klick), Trendlinien, Strahlen, Fibonacci; Kennlinien SMA, EMA, Bollinger, Volumen, RSI, MACD mit frei wählbaren Perioden und Farben; Kerzen, Balken, Linie oder Fläche; wird je Nutzer automatisch gespeichert |
| Nutzer | Weitere Personen per Einladungslink (einmalig, 7 Tage gültig). Jeder hat eigene Watchlist, Käufe, Alarme, Schattendepot, Strategie, Anzeigewährung und Push-Kanal. Nur der erste Nutzer (Admin) sieht Administration, Zeitplan, Nachrichtenquellen und Updates |
| Watchlist | Kurs, Tagesänderung, 30-Tage-Verlauf, RSI, Einschätzung |
| Chart | Kerzen mit Volumen, SMA 20/50/200, Bollinger, Unterstützung/Widerstand, RSI- und MACD-Fenster; Tag, Woche, Stunde, 15 Minuten |
| Analyse | SMA, EMA, RSI, MACD, Bollinger, Stochastik, ADX, ATR, OBV, Volumen → Einzelsignale und Score; News-Stimmung aus Google News, Yahoo Finance und Finnhub (zusammengeführt, ohne Duplikate) |
| Alarme | 16 Bedingungen: Kurs über/unter, Kreuzungen, RSI-Schwellen, MACD-Kreuz, Golden/Death Cross, Kurs kreuzt MA, Bollinger-Ausbruch, Volumenspitze, neue Hochs/Tiefs, Tagesbewegung; beliebiges Kerzenintervall, Pause nach Auslösung, einmalig |
| Einstellungen | ntfy (Antippen einer Nachricht öffnet TradeHelper; die Adresse wird beim ersten Aufruf übernommen), Nachrichtenquellen und Marktfeeds, Zeitplan von Report und Alarmprüfung, Zeitzone – alles ohne Neustart |
| Administration | Zustand der Dienste, **Update per Knopf** (mit Sicherung vorher und automatischem Zurückrollen), Sicherungen |

| Depot | Käufe erfassen (im Chart vorbelegt mit Kurs, Stopp, Ziel und Stückzahl aus dem Einstiegsplan), Gewinn/Verlust je Position und als Verlauf, Hinweise „Stopp erreicht“, „Ziel erreicht“, „Stopp nachziehen“; im Chart grüne Gewinn- und rote Verlustzone ab Kaufkurs |
| Schattendepot | Virtuelles Depot mit Spielgeld (Standard 10.000 €, 1 € pro Order), das die Einschätzungen jeden Handelstag automatisch handelt: Kauf bei „Gute Gelegenheit“ mit Positionsgröße nach Risikoprofil, Verkauf am nachgezogenen Stopp, am Ziel oder wenn die Einschätzung kippt. Vergleich mit „kaufen und halten“. Dazu ein Rückblick über zwei Jahre für alle neun Strategien (Lernjahr wählt aus, Prüfjahr kontrolliert), wöchentlich neu gerechnet |

**Standardbörse ist gettex** (Börse München, 8–22 Uhr, Kurse in Euro nahezu in Echtzeit), abgefragt über die öffentliche onvista-Schnittstelle. gettex-Werte werden intern als `<ISIN>.GTX` geführt, z. B. `DE0007164600.GTX` für SAP. Für gettex gibt es Tages- und Wochenkerzen, keine Stunden- oder Minutenkerzen. Andere Börsen kommen weiterhin über Yahoo.

Symbole anderer Börsen in Yahoo-Schreibweise: `AAPL`, `SAP.DE` (Xetra), `^GDAXI` (DAX), `BTC-EUR`, `EURUSD=X`, `IWDA.AS`.

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
./install.sh reset-login   # Admin-Passwort vergessen: Zugangsdaten neu festlegen (alle Daten bleiben)
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

### Einstiegsplan

Zu jedem Wert zeigt der Chart einen Einstiegsplan, passend zur Strategie (kurz auch in Heute, Watchlist und Morgenreport):

| Einstieg | Wann | Kursmarke | Alarm per Klick |
|---|---|---|---|
| Sofort | Einschätzung „Kaufen prüfen“ | aktueller Kurs | – |
| Rücksetzer | intakter Aufwärtstrend | Zone ±0,5 ATR um EMA 21 (kurz), SMA 50/Unterstützung (mittel); langfristig Teilkäufe an SMA 50 und SMA 200 | Kurs fällt in die Zone |
| Ausbruch | Widerstand höchstens 12 % über Kurs (nicht konservativ im Abwärtstrend) | Widerstand + 0,2 ATR | Kurs steigt darüber |
| Rebound | nur offensiv (oder ausgewogen + kurzfristig), RSI < 35 bzw. am unteren Bollinger-Band | unteres Band, Stopp 1 ATR | RSI steigt über 30 |

Jeder Einstieg hat Stopp, Ziel, Chance/Risiko (geprüft gegen das Mindest-CRV des Profils) und optional eine Positionsgröße. Dazu kommen **Signale, auf die man warten sollte**: Schlusskurs über der 200-Tage-Linie, Golden Cross (langfristig), MACD dreht nach oben, EMA 9 über EMA 21 (kurzfristig), Abkühlung bei RSI über 70 – ebenfalls mit Alarm per Klick. Logik: `backend/app/entry.py`.

Jeder Indikator liefert ein Signal zwischen −2 und +2, gewichtet nach Horizont und auf −1…+1 normiert, dann mit der News-Stimmung gemischt. Mit hinterlegter Depotgröße schlägt TradeHelper eine Positionsgröße vor (Stückzahl so, dass ein Stopp höchstens das Depotrisiko kostet). Die Logik steht in `backend/app/analysis.py`.

## Entwicklung

```bash
cd backend && pip install -r requirements-dev.txt && pytest
uvicorn app.main:app --reload              # Backend auf :8000
cd frontend && npm install && npm run dev  # Oberfläche auf :5173
```

## Grenzen

- **Keine durchgehenden Echtzeitkurse.** Laut [Yahoo](https://help.yahoo.com/kb/SLN2310.html) sind Nasdaq, Krypto und Devisen in Echtzeit, Xetra, Frankfurt und die übrigen deutschen Börsen sowie Euronext 15 Minuten verzögert, London 20 und SIX 30 Minuten. Der Chart zeigt Stand und Verzögerung je Wert und lädt jede Minute neu; Alarme werden im eingestellten Intervall geprüft. Für Daytrading ist das nicht geeignet.
- Kurse über yfinance (inoffizielle Yahoo-Schnittstelle): Ausfälle sind möglich, Intraday-Daten nur für begrenzte Zeiträume.
- Finnhub-News decken vor allem US-Werte ab; Google News findet Meldungen über den Firmennamen, auch für europäische Werte und ETFs. Die Stimmung wird regelbasiert aus den Schlagzeilen geschätzt.
- Die News-Stimmung ist ein einfaches Wortlisten-Verfahren.

Lizenz: MIT
