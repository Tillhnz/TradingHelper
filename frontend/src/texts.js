// Verständliche Bezeichnungen und Erklärungen für Leute, die nicht täglich mit Charts arbeiten.

export const ACTION_UI = {
  "Kaufen prüfen": { label: "Gute Gelegenheit", short: "Kaufen?", tone: "buy", icon: "▲",
    explain: "Die meisten Signale sprechen gerade für einen Einstieg. Prüfe trotzdem, ob es zu dir passt." },
  "Halten / beobachten": { label: "Abwarten", short: "Abwarten", tone: "hold", icon: "●",
    explain: "Es gibt kein klares Signal. Beobachten und auf einen besseren Moment warten." },
  "Reduzieren prüfen": { label: "Vorsicht", short: "Vorsicht", tone: "sell", icon: "▼",
    explain: "Die Signale sind überwiegend negativ. Nicht neu einsteigen; wer den Wert hat, sollte den Stopp prüfen." },
};

export const HELD_UI = {
  "Kaufen prüfen": { label: "Halten, Nachkauf möglich", tone: "buy" },
  "Halten / beobachten": { label: "Halten", tone: "hold" },
  "Reduzieren prüfen": { label: "Verkauf prüfen", tone: "sell" },
};

export const GLOSSARY = {
  KGV: "Kurs-Gewinn-Verhältnis: Wie viele Jahresgewinne du für eine Aktie bezahlst. Unter 15 gilt als günstig, über 30 als teuer – Wachstumsfirmen haben oft ein höheres KGV.",
  Dividendenrendite: "Ausschüttung pro Jahr im Verhältnis zum Kurs. 3 % heißt: Für 100 € Aktien gibt es etwa 3 € Dividende im Jahr.",
  Börsenwert: "Marktkapitalisierung: Aktienkurs mal Anzahl aller Aktien – so viel ist das Unternehmen an der Börse wert.",
  "EBIT-Marge": "Operativer Gewinn (vor Zinsen und Steuern) je 100 € Umsatz. Zeigt, wie profitabel das Kerngeschäft ist.",
  Nettomarge: "Was nach allen Kosten und Steuern von 100 € Umsatz als Gewinn übrig bleibt.",
  Eigenkapitalrendite: "Gewinn im Verhältnis zum Eigenkapital – wie gut das Unternehmen mit dem Geld seiner Eigentümer wirtschaftet. Über 15 % ist stark.",
  Eigenkapitalquote: "Anteil des Eigenkapitals an der Bilanzsumme. Je höher, desto weniger hängt die Firma von Schulden ab.",
  KBV: "Kurs-Buchwert-Verhältnis: Börsenwert geteilt durch das bilanzielle Eigenkapital. Unter 1 heißt: Die Börse bewertet die Firma unter ihrem Buchwert.",
  PEG: "KGV geteilt durch das erwartete Gewinnwachstum. Um 1 gilt als fair bewertet, darunter als günstig im Verhältnis zum Wachstum.",
  TER: "Laufende Kosten eines Fonds pro Jahr in Prozent des angelegten Geldes. Sie werden automatisch vom Fondsvermögen abgezogen.",
  Thesaurierend: "Erträge wie Dividenden werden nicht ausgezahlt, sondern automatisch wieder angelegt.",
  Ausschüttend: "Erträge wie Dividenden werden regelmäßig auf dein Konto ausgezahlt.",
  Risikoklasse: "Einstufung von 1 (sehr geringes Risiko) bis 7 (sehr hohes Risiko) aus dem Basisinformationsblatt des Fonds.",
  "Max. Verlust": "Größter Rückgang vom Höchst- zum Tiefststand innerhalb des Zeitraums.",
  "Stopp": "Ein Kurs, bei dem du verkaufst, um größere Verluste zu vermeiden. Fällt der Kurs darunter, meldet sich TradeHelper.",
  "Ziel": "Ein Kurs, bei dem du Gewinne mitnehmen oder deinen Stopp nachziehen kannst.",
  "Chance/Risiko": "Wie viel du bis zum Ziel gewinnen kannst im Verhältnis zu dem, was du bis zum Stopp verlieren würdest. 2 heißt: doppelt so viel Chance wie Risiko.",
  "Rücksetzer": "Ein vorübergehender Rückgang in einem Aufwärtstrend. Oft ein günstigerer Einstieg als nach einem starken Anstieg.",
  "Ausbruch": "Der Kurs steigt über eine Marke, an der er zuletzt mehrmals gescheitert ist (Widerstand). Kann einen neuen Anstieg einleiten.",
  "Rebound": "Gegenbewegung nach einem starken Rückgang. Riskanter, weil der Trend noch nach unten zeigt.",
  "Unterstützung": "Kursbereich, in dem der Kurs zuletzt nach unten gebremst wurde.",
  "Widerstand": "Kursbereich, in dem der Kurs zuletzt nach oben gebremst wurde.",
  "Trend": "Die grobe Richtung des Kurses über Monate. Ein Aufwärtstrend liegt vor, wenn der Kurs über seinem 200-Tage-Durchschnitt liegt.",
  "SMA": "Gleitender Durchschnitt: der mittlere Kurs der letzten 20, 50 oder 200 Tage. Glättet Schwankungen und zeigt den Trend.",
  "RSI": "Relative Stärke (0–100). Über 70 gilt ein Wert als heißgelaufen, unter 30 als stark gefallen.",
  "MACD": "Trendfolge-Indikator. Kreuzt die MACD-Linie ihre Signallinie nach oben, dreht das Momentum nach oben.",
  "Bollinger": "Bänder um den Durchschnitt, die die übliche Schwankung zeigen. Kurse außerhalb sind ungewöhnlich weit gelaufen.",
  "ADX": "Misst, wie stark ein Trend ist (über 25 = deutlicher Trend), egal ob auf- oder abwärts.",
  "ATR": "Durchschnittliche Tagesschwankung. Hohe Werte bedeuten große Kurssprünge.",
  "Score": "Zusammenfassung aller Signale von −1 (sehr negativ) bis +1 (sehr positiv).",
  "Verzögerung": "Wie aktuell der Kurs ist. gettex, Nasdaq und Krypto kommen in Echtzeit, viele Börsen 15 Minuten verzögert. Der Kurs ändert sich nur, wenn tatsächlich gehandelt wird – bei weniger gehandelten Werten kann das letzte Geschäft ein paar Minuten zurückliegen. TradeHelper fragt alle 15 Sekunden nach.",
  "Geld/Brief": "Geld: so viel bekommst du gerade beim Verkauf. Brief: so viel zahlst du gerade beim Kauf. Diese Kurse stellt der Handelsplatz laufend, auch wenn gerade niemand handelt – sie sind also oft aktueller als der letzte Kurs.",
  "Mitlaufender Stopp": "Ein Stopp, der mit dem Kurs nach oben wandert: Er liegt immer einen festen Prozentsatz unter dem höchsten Kurs seit dem Kauf und sinkt nie. So sicherst du Gewinne, ohne den Stopp selbst nachzuziehen. Beim Broker heißt das Trailing-Stop-Order.",
  "gettex": "Börse München mit langen Handelszeiten (8–22 Uhr) und günstigen Gebühren bei vielen Neobrokern.",
};

export const KIND_UI = {
  now: "Jetzt einsteigen",
  pullback: "Bei Rücksetzer kaufen",
  breakout: "Bei Ausbruch kaufen",
  rebound: "Gegenbewegung nutzen",
};

export function displayTicker(item) {
  if (!item) return "";
  if (item.ticker) return item.ticker;
  const s = item.symbol || "";
  return s.endsWith(".GTX") ? s.slice(0, -4) : s;
}

export function displayName(item) {
  return item?.name || displayTicker(item);
}

export function greeting() {
  const h = new Date().getHours();
  return h < 11 ? "Guten Morgen" : h < 18 ? "Guten Tag" : "Guten Abend";
}
