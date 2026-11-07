// Neuerungen je Version. Beim ersten Öffnen einer neuen Version zeigt TradeHelper die Einträge seit dem letzten Besuch.
// Neueste Version zuerst.

export const CHANGELOG = [
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
