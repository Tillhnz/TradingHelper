// Neuerungen je Version. Beim ersten Öffnen einer neuen Version zeigt TradeHelper die Einträge seit dem letzten Besuch.
// Neueste Version zuerst.

export const CHANGELOG = [
  {
    version: "2.3.3",
    date: "27.11.2026",
    title: "Großer Chart: Achse passt sich den Kursen an",
    items: [
      "Die Preisachse im großen Chart richtet sich jetzt nach den sichtbaren Kursen. Vorher zogen Ziel und Stopp deiner Position sowie weit entfernte Durchschnittslinien die Achse auseinander – die Kerzen waren winzig.",
      "Wer Ziel und Stopp trotzdem immer sehen will, schaltet „Ziel/Stopp in der Skala“ ein.",
      "Ein zweiter oder dritter gleitender Durchschnitt bekommt automatisch eine andere Länge (200, 20, 100 …) statt wieder 50.",
    ],
  },
  {
    version: "2.3.2",
    date: "26.11.2026",
    title: "Lernendes Modell lernt wieder",
    items: [
      "Das Lernen brach mit „window shape cannot be larger than input array shape“ ab, sobald TradeHelper ein paar Wochen Nachrichten-Stimmung gesammelt hatte: Im älteren Teil der Daten war diese Spalte noch leer. Behoben.",
    ],
  },
  {
    version: "2.3.1",
    date: "26.11.2026",
    title: "Lernendes Modell: Fehler werden angezeigt",
    items: [
      "Scheiterte das Lernen, blieb die Modell-Seite bei „Noch nicht gelernt“ – ohne Grund. Jetzt steht dort, was schiefging, auch nach einem Neustart des Servers.",
      "Bricht ein Lauf mittendrin ab (z. B. weil dem Server der Arbeitsspeicher ausgeht), erkennt TradeHelper das beim nächsten Start und sagt es.",
      "Das Lernen braucht weniger Arbeitsspeicher.",
    ],
  },
  {
    version: "2.3.0",
    date: "25.11.2026",
    title: "Warum läuft der Kurs so?",
    items: [
      "Neu auf der Seite jedes Werts: „Warum läuft der Kurs so?“ – die Kursänderung der letzten Woche, des Monats, von drei Monaten und einem Jahr aufgeteilt in Markt (z. B. DAX), Branche und das Unternehmen selbst.",
      "Dazu die stärksten Tage der letzten drei Monate mit den Schlagzeilen genau dieser Tage – so siehst du, was hinter einem Absturz oder Sprung stand.",
      "Die untere Leiste auf dem Handy bleibt immer vollständig sichtbar, auch wenn ein Inhalt breiter ist als der Bildschirm.",
    ],
  },
  {
    version: "2.2.1",
    date: "25.11.2026",
    title: "Depotbestand von finanzen.net zero",
    items: [
      "Die Bestandsliste von finanzen.net zero (CSV „ZERO-pos-…“) wird jetzt erkannt: Die Spalte „Art“ (AKTIE, DERIVAT) wurde vorher für Kauf/Verkauf gehalten, alle Zeilen wurden übersprungen.",
      "Einstandskurs, aktueller Kurs und Wert werden aus der Liste richtig übernommen.",
      "Von Hand erfasste Käufe werden dem hochgeladenen Depot zugeordnet, auch wenn sie unter einem Börsenkürzel (z. B. AIR.DE) statt der ISIN laufen – so zählt nichts doppelt.",
    ],
  },
  {
    version: "2.2.0",
    date: "25.11.2026",
    title: "Charts: Zeitraum und Auflösung",
    items: [
      "Kleiner Chart auf der Seite eines Werts: Tag, Woche, Monat, 1 Jahr, 3 Jahre, 5 Jahre oder Gesamt – die passende Auflösung wählt TradeHelper selbst.",
      "Großer Chart: dieselben Zeiträume, dazu die Auflösung je Kerze (Sekunden, Minuten, Stunden, Tage, Wochen) – nur, was für den Zeitraum geht.",
      "Großer Chart läuft live mit: die letzte Kerze wird mit jedem neuen Kurs fortgeschrieben, ohne dass Zoom oder Zeichnungen springen.",
      "Beim Hochladen lassen sich jetzt alle Dateien auswählen – Android hatte CSV-Dateien teils ausgegraut.",
    ],
  },
  {
    version: "2.1.6",
    date: "24.11.2026",
    title: "Depot hinzufügen geht wieder",
    items: [
      "„Depot hinzufügen“ scheiterte immer mit „Server nicht erreichbar“: Der Webserver hat das Anlegen auf eine falsche Adresse umgeleitet, die der Browser verworfen hat. Behoben – CSV- und PDF-Uploads gehen wieder, auch größere Dateien.",
      "Ein automatischer Test lädt jetzt bei jedem Update eine PDF-Abrechnung über die echte Oberfläche hoch.",
    ],
  },
  {
    version: "2.1.5",
    date: "24.11.2026",
    title: "Robuster bei kurzen Aussetzern",
    items: [
      "Ist der Server kurz nicht erreichbar – etwa während er nach einem Update neu startet –, wartet TradeHelper bis zu 30 Sekunden und versucht es dann von selbst noch einmal, statt sofort „Server nicht erreichbar“ zu melden.",
      "Klappt es trotzdem nicht, sagt die Meldung jetzt, woran es vermutlich liegt (Neustart oder offline).",
      "Administration zeigt, seit wann der Server läuft – so sieht man, ob er zwischendurch neu gestartet ist.",
    ],
  },
  {
    version: "2.1.4",
    date: "24.11.2026",
    title: "Analyse erklärt sich selbst",
    items: [
      "Liegen Zinsfuß und zeitgewichtete Rendite weit auseinander, erklärt die Analyse jetzt warum – mit deinen Zahlen: wie viel Geld in der Verlustphase im Depot lag und wie viel danach.",
      "Neu beim Gewinn: wie viel im Schnitt im Depot lag. Nicht investiertes Geld zählt beim Zinsfuß nicht mit.",
      "Die Datenprüfung nennt jetzt, um wie viel Euro ein auffälliger Kauf oder Verkauf das Ergebnis verschiebt.",
    ],
  },
  {
    version: "2.1.3",
    date: "24.11.2026",
    title: "Eine Einschätzung überall",
    items: [
      "Die Liste „Meine Werte“ und die Startseite rechneten nur mit dem Chart, die Seite eines Werts zusätzlich mit den Nachrichten und dem lernenden Modell. Dadurch stand z. B. in der Liste „Kaufen?“ und auf der Seite „Abwarten“. Jetzt urteilen alle Stellen gleich – auch die Benachrichtigungen.",
      "Überstimmt das lernende Modell die Regeln, steht das als Hinweis bei der Einschätzung.",
    ],
  },
  {
    version: "2.1.2",
    date: "24.11.2026",
    title: "Analyse: Schlüsse passen zu den Zahlen, alle Seiten auf dem Handy",
    items: [
      "Der Vergleich mit dem Weltmarkt berücksichtigt jetzt Euro-Ergebnis und zeitgewichtete Rendite zusammen. Zeigen sie in verschiedene Richtungen, steht da „Gemischtes Bild“ samt Erklärung – statt „vorne“.",
      "Neue Datenprüfung: Käufe oder Verkäufe, deren Kurs nicht zum Markt am Tag passt, Verkäufe vor dem Kauf und auffällige Sprünge in den Kursdaten werden mit Datum aufgelistet.",
      "Die Vergleichstabelle zeigt den Gewinn (Wert + Verkaufserlöse − Käufe) statt des Werts – so passt sie zum „Unterschied zu dir“.",
      "Auf dem Handy gibt es unten „Mehr“ mit Markt, Modell, Charts, Käufe & Blöcke, Alarme, Einstellungen und Administration.",
    ],
  },
  {
    version: "2.1.1",
    date: "24.11.2026",
    title: "Analyse: Rendite richtig gerechnet",
    items: [
      "Zeitgewichtete Rendite korrigiert: Wenn das Depot fast leer war und dann viel nachgekauft wurde, zählte schon ein kleiner Unterschied zwischen Kauf- und Schlusskurs als riesiger Verlust. Käufe zählen jetzt zum Tagesbeginn.",
      "Vergleich mit Indizes fairer: Bei deinen Verkäufen verkauft das Vergleichsdepot denselben Anteil statt denselben Betrag – vorher konnte es mehr auszahlen, als es besaß, und schnitt dadurch zu gut ab.",
      "Unter einem Jahr steht der Zinsfuß für den Zeitraum statt hochgerechnet aufs Jahr.",
      "Neuer Hinweis bei auffälligen Tagessprüngen über 25 % – meist ein falsch erfasster Kauf oder ein Kursfehler.",
    ],
  },
  {
    version: "2.1.0",
    date: "24.11.2026",
    title: "Analyse deiner Strategie",
    items: [
      "Neuer Bereich „Analyse“: dein interner Zinsfuß (IZF), die zeitgewichtete Rendite, größter Rückgang und Schwankung – und der faire Vergleich mit MSCI World, DAX, S&P 500, Euro Stoxx 50 und Nasdaq 100: gleiches Geld an denselben Tagen.",
      "Wie du handelst: Trefferquote, Ø Gewinn und Verlust, Haltedauer von Gewinnern und Verlierern, was nach Käufen und Verkäufen passierte, Nachkäufe, Streuung, Gebühren – mit Befunden in Klartext.",
      "Überall gleiche Reihenfolge der Werte, frei wählbar: eigene Reihenfolge, alphabetisch, Veränderung heute oder gesamt (unter „Meine Werte“).",
      "Auf der Startseite steht jetzt bei jedem Baustein, von wann die Kurse stammen.",
      "Beträge verbergen direkt am Vermögen mit dem Auge ein- und ausschalten – statt nur Punkte zu sehen.",
      "Der kleine Chart auf der Seite eines Werts zeigt nur noch den Kursverlauf. Signale, Einstiegsmarken und Indikatoren gibt es im Vollbild-Chart.",
    ],
  },
  {
    version: "2.0.0",
    date: "23.11.2026",
    title: "TradeHelper 2: neu gedacht",
    items: [
      "Neues, ruhiges Design mit hellem und dunklem Modus (Einstellungen → Ansicht) und neuen Schriften.",
      "Startseite selbst gestalten: „Anpassen“ antippen, Bausteine hinzufügen, verschieben und in der Größe ändern – z. B. Vermögen, Märkte, Konjunktur, Stimmung, Modell oder Mini-Charts einzelner Werte.",
      "Viel schneller: Kurse liegen jetzt dauerhaft auf dem Server und werden im Hintergrund aktuell gehalten. Seiten antworten in unter zwei Sekunden, auch direkt nach einem Neustart.",
      "Gesamtportfolio: Depots von Consorsbank, Commerzbank, finanzen.net zero und anderen per CSV- oder PDF-Upload (doppelte Käufe werden erkannt). Alle Depots zusammen mit Aufteilung nach Depot, Anlageart und Land.",
      "Zwei-Faktor-Anmeldung mit Authenticator-App, Wiederherstellungscodes und „Gerät merken“.",
      "Selbstlernendes Modell: lernt aus Kursen, Marktumfeld, Konjunkturzahlen, Nachrichten und sozialen Netzwerken, prüft jede Nacht seine eigenen Entscheidungen („Wäre Verkaufen besser gewesen?“) und bekommt nur so viel Gewicht, wie es nachweislich kann.",
      "Neue Seite „Markt“: Indizes, Rohstoffe, Konjunktur (EZB, Eurostat, FRED, Weltbank) und Stimmung (Fear & Greed, StockTwits, Bluesky, Reddit, Wikipedia-Aufmerksamkeit).",
    ],
  },
  {
    version: "0.20.1",
    date: "14.11.2026",
    title: "Besser auf dem Laptop",
    items: [
      "Die Seitenleiste lässt sich auf niedrigen Laptop-Bildschirmen scrollen – Abmelden und Version sind nicht mehr abgeschnitten.",
      "Auf üblichen Laptop-Breiten ist die Seitenleiste etwas schmaler und der Rand kleiner, dadurch bleibt mehr Platz für Charts und Tabellen.",
    ],
  },
  {
    version: "0.20.0",
    date: "12.11.2026",
    title: "Sofort da – und Zeichnen mit dem Finger",
    items: [
      "Übersicht, Meine Werte, Depot und Nachrichten zeigen beim Öffnen sofort den zuletzt geladenen Stand. Frische Kurse und Meldungen kommen im Hintergrund dazu – oben steht „aktualisiere …“ bzw. der Stand.",
      "Großer Chart auf dem Handy: Linien einfach ziehen (Anfang aufsetzen, Ende loslassen) – eine gestrichelte Vorschau mit Preis zeigt, wo sie landet. Antippen klappt weiterhin.",
      "Neu: Magnet (Punkte rasten an Hoch, Tief, Eröffnung oder Schluss der Kerze ein) und „Rückgängig“.",
      "Nach dem Zeichnen erscheint direkt unter dem Chart eine Leiste für Farbe, Alarm und Löschen – kein Scrollen zur Liste mehr.",
      "Beim Zeichnen bewegt sich weder Chart noch Seite mit; ohne Werkzeug scrollt die Seite beim senkrechten Wischen wieder ganz normal.",
    ],
  },
  {
    version: "0.19.1",
    date: "12.11.2026",
    title: "Übersicht lädt schneller und zuverlässiger",
    items: [
      "Die Übersicht prüft mehrere Werte gleichzeitig und merkt sich das Ergebnis 2 Minuten – beim Wiederöffnen ist sie sofort da („Aktualisieren“ holt frische Daten).",
      "Antwortet onvista nicht, wartet TradeHelper nicht mehr bei jedem Wert bis zur Zeitüberschreitung, sondern pausiert kurz und zeigt den letzten Stand.",
      "Klappt der Abruf gar nicht, siehst du statt „Server nicht erreichbar“ den zuletzt verschickten Bericht mit Hinweis.",
    ],
  },
  {
    version: "0.19.0",
    date: "12.11.2026",
    title: "Mehr Kerzenlängen",
    items: [
      "Im Profi-Modus und im großen Chart wählst du die Kerzenlänge: 1 Sekunde, 1, 3, 5 und 15 Minuten, 1 und 2 Stunden, Tag oder Woche.",
      "Sekundenkerzen gibt es für gettex-Werte – sie entstehen direkt aus den Einzelgeschäften des Tages.",
      "Zu jeder Kerzenlänge bietet die Auswahl nur Zeiträume an, für die es auch Daten gibt.",
    ],
  },
  {
    version: "0.18.4",
    date: "12.11.2026",
    title: "Unter dem Stopp: verkaufen oder halten?",
    items: [
      "Fällt ein Wert unter deinen Stopp, gibt TradeHelper jetzt eine klare Empfehlung mit Begründung: verkaufen – oder ausnahmsweise halten mit neuem, engem Stopp.",
      "Halten wird nur empfohlen, wenn deutlich mehr für einen Fehlausbruch spricht: Kurs nur knapp unter dem Stopp, Signale positiv, überverkauft, Unterstützung direkt darunter, Aufwärtstrend intakt. Im Zweifel gilt der Stopp.",
      "Den vorgeschlagenen neuen Stopp übernimmst du mit einem Tipp im Block. Auch die Push-Nachricht nennt die Empfehlung.",
    ],
  },
  {
    version: "0.18.3",
    date: "12.11.2026",
    title: "Schonender Umgang mit onvista",
    items: [
      "onvista sperrt Server zeitweise, die zu viele Anfragen schicken. TradeHelper fragt jetzt höchstens etwa dreimal pro Sekunde an, merkt sich Kurse länger und legt nach einer Sperre eine Pause ein (1 bis 15 Minuten), statt weiter anzuklopfen.",
      "Während einer Sperre bleibt der letzte bekannte Stand (bis zu einem Tag) sichtbar.",
      "Statt einer roten Zeile pro Wert erscheint nur noch ein Hinweis, wenn viele Werte gleichzeitig betroffen sind.",
    ],
  },
  {
    version: "0.18.2",
    date: "12.11.2026",
    title: "Kurse wieder da",
    items: [
      "onvista hat den bisherigen Zugang für Aktiendaten gedrosselt – dadurch kam bei allen gettex-Aktien „kein Wert gefunden“. TradeHelper nutzt jetzt einen anderen, gleichwertigen Zugang.",
      "Bremst onvista künftig wieder, zeigt TradeHelper den letzten bekannten Stand statt einer Fehlermeldung.",
    ],
  },
  {
    version: "0.18.1",
    date: "12.11.2026",
    title: "Charts aufgeräumt",
    items: [
      "Die Positions-Box verdeckt den Kurs nicht mehr: zartere Flächen, kleinere Beschriftungen, die sich nicht mehr überlappen.",
      "Gewinn/Verlust steht jetzt mit am Kaufkurs statt als eigene Marke auf der Kurslinie. Am Handy reichen kurze Beschriftungen („Ziel +18,8 %“).",
      "Großer Chart: Kennlinien stehen in einer kleinen Legende oben links statt als Etiketten im Chart; Kaufkurs, Stopp und Ziel stehen an der Preisachse, und rechts bleibt Platz für die Beschriftungen.",
    ],
  },
  {
    version: "0.18.0",
    date: "11.11.2026",
    title: "Nachrichten-Stimmung deutlich treffsicherer – und lernfähig",
    items: [
      "Neues Stimmungsmodell: erkennt deutsche Wortzusammensetzungen („Spionageskandal“, „Kursrutsch“), getrennte Verben („legt kräftig zu“), Fragen wie „Droht jetzt der Absturz?“, „aber/trotz“-Sätze und viele neue Finanzbegriffe.",
      "Bei neuen, nicht vorher gesehenen Schlagzeilen liegt es jetzt in rund drei Viertel der Fälle richtig statt in der Hälfte – und dreht die Richtung praktisch nie falsch herum.",
      "Liegt es trotzdem daneben: Tipp auf „klingt positiv/negativ/neutral“ bei einer Meldung und wähle die richtige Stimmung. TradeHelper merkt sich das für diese Meldung und lernt aus wiederkehrenden Wörtern für künftige Schlagzeilen.",
    ],
  },
  {
    version: "0.17.0",
    date: "10.11.2026",
    title: "Startseite nach Wunsch, Unternehmensdaten, News in der Ausbruch-Chance",
    items: [
      "Startseite und „Meine Werte“ zeigen bei jedem Wert den aktuellen Kurs – dein Vermögen im Wert siehst du auf seiner Seite (und im Depot).",
      "Startseite anpassen (Regler-Symbol oben): Bausteine ein-/ausblenden, sortieren und Beträge verbergen – gilt auf allen Geräten.",
      "Neu auf jeder Aktienseite: Unternehmen mit Kurzbeschreibung und Kennzahlen (Börsenwert, KGV, Dividende, Umsatz, Margen …). Bei ETFs: Kosten, Volumen, Index, größte Positionen und Branchen.",
      "Die Ausbruch-Chance rechnet jetzt die Nachrichtenlage mit ein und zeigt, wie stark sie die Werte verschoben hat.",
    ],
  },
  {
    version: "0.16.0",
    date: "10.11.2026",
    title: "Neues Glas-Design und Ausbruch-Chance",
    items: [
      "Komplett neues Aussehen: durchscheinende Glasflächen, farbiger Hintergrund, Symbole überall und sanfte Animationen.",
      "Neu bei jedem Wert: die Ausbruch-Chance – wie wahrscheinlich der Kurs in den nächsten Wochen über das letzte Hoch steigt oder unter das Tief rutscht. Berechnet aus der eigenen Kursgeschichte des Werts.",
      "In allen Listen zeigt ein kleines ↗/↘-Kürzel, wenn eine Richtung klar wahrscheinlicher ist.",
      "Die Einschätzung darf jetzt kippen: Ist ein Rutsch deutlich wahrscheinlicher oder läuft ein schöner Gewinn bei nachlassendem Schwung, rät TradeHelper zum Verkauf bzw. Gewinne sichern.",
      "Auf der Seite eines Werts springst du über die Leiste oben direkt zu Chart, Ausbruch, Bestand, Einstieg und News.",
      "Live-Kurse leuchten kurz auf, wenn sie sich ändern.",
    ],
  },
  {
    version: "0.15.2",
    date: "09.11.2026",
    title: "Bericht-Fehler behoben",
    items: [
      "Der Bericht brach ab, sobald ein Wert komplett verkauft war (alle Blöcke weg). Behoben – Berichte kommen wieder.",
      "Nutzer ohne ntfy-Topic: Der Bericht gilt als erledigt (liegt auf der Webseite), nicht mehr als „mit Problem“.",
    ],
  },
  {
    version: "0.15.1",
    date: "09.11.2026",
    title: "Berichte gehen nicht mehr verloren",
    items: [
      "War TradeHelper zur Berichtszeit nicht erreichbar (z. B. wegen eines Updates oder Neustarts), wird der verpasste Bericht beim Start nachgeholt.",
      "Unter Administration → Zustand siehst du jetzt den Zeitplan und die letzten Berichte – mit dem Grund, falls etwas schiefging (z. B. Push fehlgeschlagen).",
      "„Bericht jetzt senden“ meldet, wenn die Push-Nachricht nicht rausging, statt still „verschickt“ zu sagen.",
    ],
  },
  {
    version: "0.15.0",
    date: "08.11.2026",
    title: "Verkauf mit einem Tipp, Bestand in Blöcken",
    items: [
      "Neben „Kauf“ gibt es jetzt „Verkauf“: Kurs und Uhrzeit von jetzt sind schon eingetragen, anpassen kannst du sie bei Bedarf.",
      "Unter „Mein Bestand“ steht jeder Kauf als eigener Block mit Stückzahl, Kaufkurs, Stopp, Ziel und Gewinn/Verlust – und einem eigenen „Verkauf“-Knopf.",
      "Verkauft wird immer ein ganzer Block. Hast du mehrere, wählst du im Verkauf, welchen.",
      "Verkaufte Blöcke findest du darunter eingeklappt; ein Verkauf lässt sich dort auch zurücknehmen.",
    ],
  },
  {
    version: "0.14.1",
    date: "07.11.2026",
    title: "Signale besser erkennbar, großer Chart per Klick",
    items: [
      "Kauf- und Verkaufssignale im Chart sind jetzt blau und pink – so heben sie sich deutlich von den grünen und roten Kerzen ab.",
      "Direkt am Chart jedes Werts öffnet „⛶ Groß“ den großen Chart zum Zeichnen und für Indikatoren.",
    ],
  },
  {
    version: "0.14.0",
    date: "07.11.2026",
    title: "Aufgeräumt: kompakte Listen, Details auf Antippen",
    items: [
      "Übersicht, Meine Werte und Depot zeigen jeden Wert als eine kompakte Zeile: Name, Kurs oder Wert, Gewinn/Verlust und nur dann ein Hinweis, wenn etwas zu tun ist.",
      "Die Übersicht beginnt mit „Heute wichtig“ – alles andere steht darunter.",
      "Im Depot ist jeder Wert eine Zeile, auch bei mehreren Käufen. Antippen öffnet alles: Chart mit Kaufbox, Einschätzung, Käufe, Verkauf, Stopp und Ziel.",
      "Auf der Seite eines Werts kommt am Handy der Chart zuerst; „Mein Bestand“ ist kompakt, Details klappst du bei Bedarf auf. Chart-Optionen stecken hinter „Anzeige“.",
      "Das Schattendepot zeigt, wann es handelt: immer mit dem Morgen- und dem Nachmittagsbericht.",
    ],
  },
  {
    version: "0.13.0",
    date: "06.11.2026",
    title: "Kaufbox im Chart, Schnellkauf, zwei Berichte am Tag",
    items: [
      "Eigene Käufe erscheinen im Chart wie das Positions-Werkzeug von TradingView: ab dem Kaufzeitpunkt grün bis zum Ziel, rot bis zum Stopp, dazu dein aktueller Gewinn oder Verlust als kräftige Fläche mit Betrag.",
      "Schnellkauf: „Kauf“ antippen übernimmt Kurs und Uhrzeit von jetzt. Kaufkurs, Datum und Uhrzeit kannst du jederzeit überschreiben.",
      "Morgenbericht um 7:00 und neu ein Nachmittagsbericht um 16:00 (Zeiten in den Einstellungen).",
      "Das Schattendepot handelt zu den Berichtszeiten. Ist die Börse zu, legt es Orders an: Kauf-Limit knapp über dem letzten Schlusskurs, Verkauf zur Eröffnung, Stopp und Ziel als Stop- bzw. Limit-Order. Ausgeführt wird im Tagesverlauf.",
      "Dieses Fenster: Neuerungen siehst du ab jetzt nach jedem Update einmal.",
    ],
  },
  {
    version: "0.12.0",
    date: "06.11.2026",
    title: "Mehrere Nutzer, Chart-Arbeitsplatz, Push öffnet die Seite",
    items: [
      "Weitere Personen per Einladungslink – jeder mit eigener Watchlist, eigenem Depot und eigenen Push-Nachrichten.",
      "Neuer Menüpunkt „Charts“: Linien, Trendlinien, Fibonacci und Kennlinien selbst einzeichnen, pro Wert gespeichert.",
      "Antippen einer Push-Nachricht öffnet TradeHelper; der Morgenbericht erscheint als Fenster auf der Seite.",
    ],
  },
  {
    version: "0.11.0",
    date: "05.11.2026",
    title: "Live-Kurse und mitlaufender Stopp",
    items: [
      "Kurse aktualisieren sich alle 15 Sekunden, bei gettex mit Geld- und Briefkurs.",
      "Tagesverlauf (1 T, 1 W) auch für gettex; Darstellung als Kerzen, Balken, Linie oder Fläche wählbar.",
      "Empfohlener mitlaufender Stopp beim Kauf; Ziele werden bei veränderter Lage angepasst und gemeldet.",
      "Nachrichten übersichtlicher und genauer bewertet.",
    ],
  },
  {
    version: "0.10.0",
    date: "04.11.2026",
    title: "Schattendepot",
    items: ["Ein virtuelles Depot handelt die Einschätzungen mit Spielgeld; der Rückblick vergleicht neun Strategien."],
  },
];

const cmp = (a, b) => {
  const pa = a.split(".").map(Number), pb = b.split(".").map(Number);
  for (let i = 0; i < 3; i += 1) if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) - (pb[i] || 0);
  return 0;
};

/** Einträge, die seit `seen` dazugekommen sind (ohne `seen`: nur die aktuelle Version). */
export function newSince(seen, current) {
  const upto = CHANGELOG.filter((c) => cmp(c.version, current) <= 0);
  if (!seen) return upto.slice(0, 1);
  return upto.filter((c) => cmp(c.version, seen) > 0);
}
