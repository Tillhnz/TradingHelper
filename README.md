# TradeHelper

Selbst gehosteter Trading-Assistent für Proxmox: Gesamtportfolio über alle Depots, Watchlist, Chartanalyse, Alarme wie bei TradingView, Konjunktur- und Stimmungsdaten, ein selbstlernendes Modell und jeden Morgen eine Einschätzung per Push aufs Handy. Bedienung, Einstellungen und Updates laufen komplett über die Weboberfläche.

> ⚠️ Die Einschätzungen entstehen automatisch aus Regeln und einem lernenden Modell. Sie sind **keine Anlageberatung**.

## Neu in 2.0

- **Schnell:** Kurse liegen dauerhaft auf dem Server (`data/market.db`) und werden von einem Hintergrunddienst aktuell gehalten. Jede Seite antwortet nach spätestens ~1,5 s; was dann noch rechnet, kommt kurz danach nach.
- **Startseite selbst gestalten:** Bausteine hinzufügen, ziehen, Größe wählen (Vermögen, Aufteilung, Heute wichtig, Märkte, Konjunktur, Stimmung, Modell, Rückblick, Nachrichten, Mini-Charts …).
- **Neues Design** im Stil von Claude: warmes Papier, eine Akzentfarbe, Serifen-Überschriften (Source Serif 4) und Inter – hell, dunkel oder wie das System.
- **Gesamtportfolio:** Depots von Consorsbank, Commerzbank, finanzen.net zero & Co. per CSV-/PDF-Upload, dazu manuell erfasste Käufe – ohne Doppelzählung.
- **Zwei-Faktor-Anmeldung** (Authenticator-App) mit Wiederherstellungscodes und „Gerät merken“ – standardmäßig Pflicht.
- **Selbstlernendes Modell**, das seine Entscheidungen nachrechnet („Wäre Verkaufen besser gewesen?“) – siehe unten.
- **Markt:** Indizes und Rohstoffe, Konjunktur (EZB, Eurostat, FRED, Weltbank), Börsenstimmung (Fear & Greed) und Stimmung im Netz (StockTwits, Bluesky, Reddit, Wikipedia-Aufmerksamkeit).

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
                 ┌──────────── Browser (React) ────────────┐
                 │ zeigt sofort den letzten Stand (Cache),  │
                 │ frische Daten kommen im Hintergrund      │
                 └───────────────────┬──────────────────────┘
                                     │ /api (nginx)
┌────────────────────────────────────▼───────────────────────────────────────┐
│ FastAPI   routes: Auth/2FA · Portfolio/Upload · Markt/Modell · bisherige     │
│           liest NUR aus Speichern – Antwort nach spätestens ~1,5 s          │
├──────────────────────────────┬─────────────────────────────────────────────┤
│ snapshot.py  vorberechnete   │ refresher.py  Hintergrunddienst              │
│ Analysen (Fingerabdruck)     │ Kurse 30 s · Kerzen 10 min · News 8 min ·    │
│                              │ Stimmung 30 min · Makro 6 h                  │
├──────────────────────────────┴─────────────────────────────────────────────┤
│ market.db  Tageskerzen (5 J., inkrementell), Kurse, Stammdaten, Makro,     │
│            Stimmung, Vorhersagen       tradehelper.db  Nutzer, Depots, …   │
├────────────────────────────────────────────────────────────────────────────┤
│ Quellen: onvista/gettex · Yahoo · Google News/Finnhub · EZB · Eurostat ·   │
│ FRED · Weltbank · CNN Fear&Greed · StockTwits · Bluesky · Reddit · Wiki    │
│ Depots: Upload von Umsätzen/Abrechnungen (CSV/PDF)                         │
├────────────────────────────────────────────────────────────────────────────┤
│ scheduler.py  Berichte · Alarme · Schattendepot · Modell lernen 02:40 ·    │
│               Entscheidungen festhalten 22:40                              │
└────────────────────────────────────────────────────────────────────────────┘

backend/    FastAPI, Analyse, Modell (brain.py), Broker (brokers/), Hintergrunddienst, SQLite
frontend/   React + Vite, Charts mit lightweight-charts, ausgeliefert von nginx
updater/    kleiner Dienst für den Update-Knopf (git pull, neu bauen, zurückrollen)
proxmox/    Skript für den Proxmox-Host
install.sh  Installation und Wartung
```

## Depots hochladen (CSV/PDF)

Unter **Portfolio → Depot hinzufügen** Broker wählen (Consorsbank, Commerzbank, finanzen.net zero oder „Anderer Broker“) und Dateien hochladen:

- **Umsatzliste als CSV** (Datum, ISIN, Stück, Kurs, Kauf/Verkauf) – Trennzeichen, deutsche/englische Zahlen und Spaltennamen werden erkannt.
- **Wertpapierabrechnungen als PDF** – auch viele auf einmal.
- **Bestandsliste als CSV** (ISIN und Stückzahl ohne Kauf/Verkauf) – wird als aktueller Bestand des Depots übernommen.

Jeder Kauf wird ein Block, ein Verkauf schließt bevorzugt den Block mit gleicher Stückzahl (sonst die ältesten). Dateien dürfen mehrfach hochgeladen werden – bereits importierte Käufe werden übersprungen. TradeHelper verbindet sich mit keiner Bank.

## Zwei-Faktor-Anmeldung

Standardmäßig Pflicht für alle Konten (abschaltbar unter *Einstellungen → Sicherheit*). Beim ersten Anmelden QR-Code scannen, Code bestätigen, zehn Wiederherstellungscodes sichern. „Gerät merken“ spart den Code für 30 Tage (einstellbar). Handy verloren: Admin setzt die 2FA unter *Administration → Nutzer* zurück; für den Admin selbst setzt `./install.sh reset-login` Passwort **und** 2FA zurück.

## Das lernende Modell

- **Ziel:** Für jeden Wert und Horizont (5/20/60 Handelstage) die Wahrscheinlichkeit für „deutlich fallen“ (= Verkaufen wäre besser gewesen), „seitwärts“, „deutlich steigen“. „Deutlich“ richtet sich nach der Schwankung des Werts.
- **Merkmale:** Technik (Renditen, Schwankung, RSI, MACD, Durchschnitte, Bollinger, Volumen …), Markt (S&P 500, DAX, VIX, Zinsen, Dollar, Öl, Gold, Kupfer, Branchen-ETF), Makro (EZB-/Fed-Zins, Inflation, Zinskurve, Risikoaufschläge, Stimmungsindizes, Arbeitslosigkeit – jeweils erst ab Veröffentlichung) und Stimmung (News und soziale Netzwerke, ab Beginn der Aufzeichnung).
- **Lernen:** Gradient Boosting (scikit-learn) auf rund 60 Werten plus allen beobachteten/gehaltenen, 5 Jahre Tagesdaten, jede Nacht neu.
- **Sich selbst prüfen:** Walk-forward – trainiert nur auf der Vergangenheit, getestet auf den folgenden drei Monaten (mit Sicherheitsabstand). Vier Varianten treten an; Wahrscheinlichkeiten werden so weit zur Basisrate geschrumpft, wie die letzte Validierung verlangt.
- **Hinterfragen:** Jede Abend-Einschätzung (Regeln, Modell, kombiniert) landet im Entscheidungsjournal und wird nach Ablauf des Horizonts nachgerechnet („Verkaufen wäre besser gewesen (−8 %)“, „Halten wäre besser gewesen“). Fehlentscheidungen zählen beim nächsten Lernen doppelt; wer öfter recht hatte, bekommt mehr Gewicht.
- **Gewicht:** Können auf ungesehenen Daten × Bilanz im Journal, höchstens 60 % (einstellbar). Ein Kauf braucht immer zusätzlich die Regeln – das Modell darf nur bremsen oder zum Verkauf raten.

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
- Die News-Stimmung ist ein Wortlisten-Verfahren (lernt aus Korrekturen in der App).
- Reddit lässt seit Mai 2026 nur noch angemeldete Apps zu; ohne eigene Zugangsdaten fehlt diese Quelle. X/Twitter ist kostenpflichtig und nicht angebunden.
- Das Modell kann sich irren. Es zeigt deshalb immer, wie gut es auf ungesehenen Daten war – und ist es nicht besser als der Zufall, zählt es nicht.

Lizenz: MIT
