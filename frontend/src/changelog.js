// Neuerungen je Version. Beim ersten Öffnen einer neuen Version zeigt TradeHelper die Einträge seit dem letzten Besuch.
// Neueste Version zuerst.

export const CHANGELOG = [
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
