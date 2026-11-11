"""Stimmung einer Finanzmeldung (−1 … +1) aus Sicht eines Aktionärs – Deutsch und Englisch.

Ablauf:
1. Lockschlagzeilen ohne Aussage („Should you buy …?“, „Kaufen oder verkaufen?“) zählen gar nicht.
2. Feste Wendungen zuerst („hebt Kursziel an“, „Gericht weist Klage ab“, „setzt Talfahrt fort“). Was sie abdecken,
   wird danach nicht noch einmal als Einzelwort gezählt.
3. Einzelwörter und Wortstämme – auch mitten in deutschen Zusammensetzungen („Spionage*skandal*“, „Kurs*rutsch*“).
4. Umgebung eines Treffers:
   - Verneinung davor („nicht“, „kein“, „not“) dreht ihn um,
   - Verstärker („kräftig“, „deutlich“, „sharply“) machen ihn 1,5-mal so stark,
   - Möglichkeitsform („könnte“, „could“) und Fragen schwächen ab, behalten aber die Richtung
     („Droht jetzt der Absturz?“ bleibt negativ),
   - Nebensätze mit „trotz/despite“ zählen zu 30 %, der Teil vor „aber/but“ zu 70 % – die Hauptaussage steht danach.
5. Ergebnis: Summe / (Betragssumme + 1,2), begrenzt auf ±1. Ein einzelnes klares Signal ergibt etwa ±0,45.

Gemessen an 214 bewerteten Schlagzeilen (tests/data/sentiment_headlines.tsv); dazu kommen Korrekturen aus der App
(siehe learn.py), mit denen das Modell auf deine Nachrichtenquellen nachgeschärft wird.
"""
from __future__ import annotations

import re

_X = r"[\wäöüß-]*"  # Rest eines Wortes (für Zusammensetzungen)
_N = r"(?:\S+ ){0,3}"  # bis zu drei Wörter dazwischen

# Lockschlagzeilen: Die ganze Meldung zählt nur zu 30 % – das ist Meinungsmache, keine Nachricht
CLICKBAIT = [
    r"should you buy|is it time to (buy|sell)|time to buy|buy (it )?now\?|(best|top) \S* ?stocks? to (buy|own|hold)",
    r"stocks? to (buy|hold|own)( forever| now)?|kaufen oder (nicht|verkaufen)|jetzt kaufen\?",
]
# Wendungen ohne Aussage: zählen 0 und „verbrauchen“ den Text
NEUTRAL = CLICKBAIT + [
    r"what to expect|here'?s what|earnings call transcript|transcript",
    r"was anleger (\S+ )?(heute |jetzt )?wissen (müssen|sollten)|die wichtigsten termine",
    r"(kurs)?ziel (bestätigt|unverändert|bleibt)|bestätigt (\S+ ){0,2}(kurs)?ziel|keeps? \S+ (weight )?rating|reiterates?|maintains?",
    r"ernennt|appoints?|names new|chartanalyse|hauptversammlung|investor (day|conference)|to present at",
    # Ausgangslage, nicht die Nachricht: „kaufen nach Kursrutsch“, „rebound after selloff“
    r"(nach|after) (dem |der |a |the )?(kursrutsch|rücksetzer|einbruch|selloff|sell-off|slump|drop|rally|rallye)",
]

PHRASES: list[tuple[str, float]] = [
    # Analysten: Kursziele und Einstufungen
    (rf"(senkt|senken|reduziert|kappt|kürzt|streicht){_X} {_N}(kurs)?ziel", -2),
    (r"(kurs)?ziel (für \S+ )?(wird |werden )?(gesenkt|reduziert|gekappt|gekürzt)", -2),
    (r"(cuts?|lowers?|lowered|trims?|trimmed|slash(es|ed)?|reduces?|reduced) (\S+ ){0,4}(price )?targets?", -2),
    (r"price targets? (cut|lowered|trimmed|reduced|slashed)", -2),
    (rf"(hebt|heben|erhöht|erhöhen|schraubt){_X} {_N}(kurs)?ziel", 2),
    (r"(kurs)?ziel (für \S+ )?(wird |werden )?(angehoben|erhöht|hochgesetzt)", 2),
    (r"(raises?|raised|lifts?|lifted|boosts?|boosted|hikes?|hiked) (\S+ ){0,4}(price )?targets?", 2),
    (r"stuft (\S+ ){0,4}(ab|herab|runter)\b|herabgestuft|abgestuft|downgrades?|downgraded|cut to (sell|underweight|neutral|hold)", -2),
    (r"stuft (\S+ ){0,4}(hoch|herauf|rauf)\b|hochgestuft|heraufgestuft|upgrades?|upgraded|raised to (buy|overweight|outperform)", 2),
    (r"(kaum|wenig|kein) (noch )?(kurs)?potenzial|verkaufsempfehlung|sell rating|underperform|underweight|untergewichten", -1.5),
    (r"kaufempfehlung|buy rating|outperform|overweight|übergewichten|trauen (\S+ ){0,3}zu|\w*potenzial", 1),
    (r"(senkt|kappt) (\S+ )?(bonitätsnote|rating)|cuts? (\S+ )?rating|to junk|ramschniveau", -1.5),
    (r"hebt (\S+ )?(bonitätsnote|rating) an|rating (raised|upgraded)", 1.5),
    # Prognosen und Zahlen
    (r"\w*gewinnwarnung|\w*umsatzwarnung|profit warning", -2),
    (rf"(senkt|kappt|kürzt|reduziert){_X} (\S+ ){{0,3}}(prognose|ausblick|jahresziele?|renditeziel|umsatzziel)|(prognose|ausblick) (gesenkt|gekappt|gekürzt)", -2),
    (r"(cuts?|lowers?|lowered|slashes?|trims?) (\S+ ){0,2}(guidance|forecast|outlook)", -2),
    (rf"(hebt|erhöht){_X} (\S+ ){{0,3}}(prognose|ausblick|jahresziele?)|(prognose|ausblick) (angehoben|erhöht)|prognoseanhebung", 2),
    (r"(raises?|raised|lifts?|boosts?) (\S+ ){0,2}(full-year )?(guidance|forecast|outlook)|guidance (lift|raise|hike)", 2),
    (r"(beats?|tops?|topped|exceeds?|exceeded|surpass(es|ed)?) (\S+ )?(estimates|expectations|forecasts?|consensus)|beats on", 2),
    (r"übertr(ifft|afen?) (die )?(erwartungen|prognosen?|schätzungen)|über (den )?erwartungen", 2),
    (r"(misses|missed|miss) (\S+ )?(estimates|expectations|forecasts?|consensus)|earnings miss|falls? short of", -2),
    (r"verfehlt (\S+ )?(erwartungen|\w*erwartungen|prognosen?|schätzungen|ziele?)|unter (den )?erwartungen", -2),
    (r"(mehr|besser|robuster|stärker) als (erwartet|befürchtet|gedacht)|better than expected|less than feared|weniger als befürchtet", 1.5),
    (r"(schlechter|schwächer) als (erwartet|befürchtet)|worse than expected", -1.5),
    (r"verdient (\S+ ){0,3}weniger|weniger (gewinn|umsatz)|(gewinn|umsatz) (bricht ein|schrumpft|sinkt)", -1.5),
    (r"(steigert|erhöht) (\S+ ){0,2}(gewinn|umsatz|ergebnis)|(gewinn|umsatz|ergebnis) (steigt|wächst|legt zu)", 1.5),
    (r"(still )?(hasn'?t|has not|have not|haven'?t|didn'?t|did not|fails? to|failed to|has yet to) (\S+ ){0,2}"
     r"(publish|deliver|disclose|provide|meet|show|report|release)\w*", -1),
    # Dividende, Rückkauf, Übernahme
    (r"(kürzt|streicht|senkt|cuts?|suspends?|slashes?) (\S+ )?(die )?dividend\w*|dividend (cut|suspension)", -2),
    (r"dividendenerhöhung|(erhöht|hebt|steigert) (\S+ )?dividende|dividend (hike|increase)|(raises?|reinstates?|boosts?) (\S+ )?dividend", 1.5),
    (r"aktienrückkauf|rückkaufprogramm|(share )?buybacks?", 1),
    (r"übernahmeangebot|takeover (bid|offer)|kaufangebot", 1.5),
    (r"(übernahme|fusion|deal) (\S+ )?(geplatzt|abgesagt|gescheitert)|deal (collapses|falls through|scrapped)", -1.5),
    # Recht und Behörden
    (r"(weist|wiesen) (\S+ )?klage (\S+ ){0,3}ab|klage (\S+ )?abgewiesen|dismiss(es|ed)? (the )?(lawsuit|case|suit)", 1.5),
    (r"gewinnt (\S+ ){0,2}(rechtsstreit|patentstreit|prozess|klage|verfahren)|wins? (\S+ ){0,2}(lawsuit|case|patent|appeal)", 1.5),
    (r"verliert (\S+ ){0,2}(rechtsstreit|patentstreit|prozess|klage|verfahren)|loses? (\S+ ){0,2}(lawsuit|case|patent|appeal)", -1.5),
    (r"verurteilt|schadenersatz|(ordered|orders? \S+) to pay|jury orders?|muss (\S+ ){0,3}zahlen", -1.5),
    (r"settles? (\S+ )?(litigation|lawsuit|case|dispute)|vergleich (\S+ )?(erzielt|geschlossen)", 0.5),
    (r"(fda|ema|behörde) (\S+ ){0,2}(clears?|approves?|genehmigt|lässt \S+ zu)|\w*zulassung|approvals?|approved", 1.5),
    (r"studie gescheitert|\w*studie (\S+ )?(scheitert|gescheitert|verfehlt)|(disappointing|failed) trial|trial (fails?|failure)", -2),
    (r"positive(n)? (studiendaten|studienergebnisse|daten)|positive (trial|data|results)", 1.5),
    (r"export (curbs|restrictions|controls|ban)|\w*export(beschränkung|regel|kontrolle|verbot|stopp)\w*", -1),
    # Kursbewegungen als Wendung – deutsche Verben mit abgetrenntem Teil („legt kräftig zu“, „bricht nach … ein“)
    (r"(legt|legen|zieht|ziehen|zog|springt|springen|atmet|atmen|lebt|leben|zieht) (\S+ ){0,4}(zu|an|auf)\b(?! (dem|der|den|die|das)\b)", 1),
    (r"(bricht|brechen|brach|stürzt|stürzen|sackt|sacken|rutscht|rutschen|gibt|geben|gab|fällt|fallen|bröckelt|bröckeln|"
     r"streicht|streichen|dampft|dampfen|schmiert|schmieren) (\S+ ){0,4}(ein|ab|nach|zusammen)\b", -1),
    (r"end(s|ed)? (\S+ )?(strike|streik|dispute|lockdown)|(streik|konflikt|handelsstreit) (\S+ )?(beendet|beigelegt)", 1.5),
    (r"(chef|ceo|vorstand|cfo|finanzchef|gründer) (\S+ ){0,2}(geht|verlässt|muss gehen|exit|departs?|leaves?)", -1),
    (r"(erholt sich|erholen sich|erholung) (\S+ )?(von|nach) (\S+ )?\S*(rutsch|einbruch|verlust|tief)\w*", 1.5),
    (r"(anleger|investoren|investors|käufer) (\S+ ){0,2}(kaufen|greifen zu|steigen ein|feiern|buy)", 1),
    (r"(anleger|investoren|investors) (\S+ ){0,2}(strafen|verkaufen|fliehen|flee|sell|dump)", -1.5),
    (r"(rally|rallye|aufschwung|höhenflug|boom|party) (\S+ ){0,2}(end|ends|over|vorbei|zu ende|beendet)", -1.5),
    (r"(sanktionen|zölle|beschränkungen|restrictions|tariffs|curbs) (\S+ )?(gelockert|aufgehoben|lifted|eased|removed|scrapped)"
     r"|(lockert|lockern|hebt) (\S+ )?(sanktionen|zölle|beschränkungen) (\S+ )?(auf)?", 1.5),
    (r"(growth|wachstum|nachfrage|demand|umsatz|sales|absatz|geschäft) (\S+ ){0,2}(slows|slowing|stalls|stagniert|"
     r"verlangsamt|schwächt sich ab|bricht ein|schrumpft|sinkt|fällt|falls|drops|declines|weakens)", -1.5),
    (r"(growth|wachstum|nachfrage|demand|umsatz|sales|absatz|exporte) (\S+ ){0,2}(accelerates|beschleunigt|zieht an|"
     r"steigt|wächst|wachsen|rises|jumps|surges|booms)", 1.5),
    (r"(kreditausfälle|ausfälle|verluste|kosten|schulden|defaults|losses|costs|debt|risiken|sorgen|insolvenzen|"
     r"lagerbestände|arbeitslosigkeit|abschreibungen|frachtraten fallen) (\S+ ){0,2}(steigen|steigt|wachsen|klettern|rise|rising|climb|jump|surge|mount)( [^\s,;:–-]+){0,5}", -1.5),
    (r"ruft (\S+ ){1,3}zurück|recalls? (\S+ ){0,3}(vehicles|cars|suvs|trucks|products)", -1.5),
    (r"greif(t|en) (\S+ ){0,2}zu|gefragt wie nie|sehr gefragt|hochtouren", 1.5),
    (r"(setzt|setzen) (\S+ )?(erholung|aufwärtstrend|rally|rallye|höhenflug) fort|extends? (\S+ )?gains|rally geht weiter", 1.5),
    (r"(setzt|setzen) (\S+ )?(talfahrt|abwärtstrend|verluste|kursrutsch) fort|extends? (\S+ )?(losses|declines|slide)", -1.5),
    (r"(verkaufen|verkauf) (\S+ )?in panik|panikverk\w*|flüchten aus|dump(s|ed)? (\S+ )?shares", -2),
    (r"gewinnmitnahmen|profit-?taking", -1),
    (r"rekordtief|allzeittief|jahrestief|mehrjahrestief|tiefststand|all-time low|record low", -1.5),
    (r"\w*(rekordhoch|allzeithoch|höchststand)|record high|all-time high", 1.5),
    (r"trübt sich (\S+ )?ein|(stimmung|klima) (sinkt|fällt|verschlechtert)", -1),
    (r"hellt sich (\S+ )?auf|(stimmung|klima) (steigt|verbessert)", 1),
    (r"profitier(t|en) (\S+ ){0,2}von( \S+){0,3}|benefits? from( \S+){0,3}", 1.5),
    (r"verlier(t|en) (\S+ ){0,2}(\w*auftrag|kunden|\w*kunden|marktanteile?|zulassung)|loses? (\S+ ){0,2}(market share|customers?|contract|clients?)", -1.5),
    (r"(verkauft|verkaufen|setzt|setzen|liefert|liefern|sells?|ships?|delivers?) (\S+ ){0,3}(mehr|more)\b", 1),
    (r"(verkauft|verkaufen|setzt|setzen|liefert|liefern|sells?|ships?|delivers?) (\S+ ){0,3}(weniger|fewer|less)\b", -1.5),
    (r"(hebt|heben) (\S+ ){0,3}an\b", 1),
    (r"schwarze(n)? zahlen|gewinnzone|(erstmals|first) (profitabel|profitable|profit)", 1.5),
    (r"rote(n)? zahlen|in the red|verbrennt (\S+ ){0,2}geld|burns? (through )?cash", -1.5),
    (r"cuts? (\S+ ){0,2}jobs|streicht (\S+ ){0,2}jobs|baut (\S+ ){0,2}(stellen|jobs) ab", -1.5),
    (r"(leiden|leidet|litt) (\S+ )?unter|belastet|belasten|weighs? on|weigh(ed|ing) on|hurt by|hit by", -1.5),
    (r"setzt (\S+ ){0,3}unter druck|unter druck", -1),
    (r"tritt (\S+ ){0,2}zurück|rücktritt|resigns?|steps? down|ousted|abgang", -1),
    (r"schließt (\S+ ){0,2}(standort|werk|werke|anlagen|fabrik|filialen)|streicht (\S+ ){0,2}stellen|\w*stellenabbau|job cuts|layoffs?", -1.5),
    (r"short-?seller|leerverkäufer", -1.5),
    (r"trifft (\S+ ){0,2}hart", -1),
    # Makro: steigende Inflation/Zinsen/Arbeitslosigkeit sind schlecht, fallende gut
    (r"(inflation|teuerung|zinsen|leitzins|arbeitslosigkeit|arbeitslosenquote|ölpreis|unemployment|yields?)"
     r"( \S+){0,2} (steigt|steigen|klettert|klettern|zieht an|erreicht|rises?|rose|climbs?|jumps?|surges?|hits?)( [^\s,;:–-]+){0,5}", -1.5),
    (r"(inflation|teuerung|zinsen|leitzins|arbeitslosigkeit|ölpreis|unemployment|yields?)( \S+){0,2} "
     r"(sinkt|sinken|fällt|fallen|geht zurück|eases?|falls?|fell|drops?|cools?)( [^\s,;:–-]+){0,5}", 1.5),
    (r"(senkt|senken) (\S+ )?(leit)?zins|zinssenkung|rate cuts?", 1.5),
    (r"(erhöht|erhöhen|hebt) (\S+ )?(leit)?zins|zinserhöhung|rate hikes?", -1.5),
    (r"arbeitslosigkeit|arbeitsmarkt (\S+ )?(robust|stark)", 0),
    # erst nach den Makro-Wendungen: „Arbeitslosigkeit auf höchstem Stand“ ist schlecht
    (r"tiefste(n|r)? (stand|niveau)|lowest (level )?(since|in)", -1.5),
    (r"(höchste(n|r)? (stand|niveau)|highest (level )?(since|in))", 1),
]

# Einzelwörter; ein * am Anfang heißt: darf auch mitten in einem zusammengesetzten Wort stehen
WORDS: list[tuple[str, float]] = [
    # Kurs rauf
    ("legt zu|zieht an|steigt|steigen|stieg|klettert|klettern|springt|springen|erholt|erholung|haussiert|"
     "im plus|kaufsignal|bricht aus|ausbruch|im aufwind|aufwärts|höher|fester|gewinne|"
     "climbs?|rises?|rose|jumps?|surges?|soars?|soaring|rall(y|ies|ied)|gains?|rebounds?|"
     "breaks? (through|out)|breakout|higher|bullish|takes hold", 1),
    # Kurs runter
    ("fällt|fallen|fiel|sinkt|sinken|sackt ab|rutscht|rutschen|bricht ein|stürzt|verliert|verlieren|im minus|"
     "gibt nach|geben nach|verkaufssignal|abwärts|tiefer|schwächer|leichter|im abwind|"
     "falls?|fell|drops?|dropped|slides?|slid|slumps?|plunges?|tumbles?|sinks?|declines?|lower|bearish|"
     "wipes? out|slows?|slowing", -1),
    ("erholen sich|freundlich|genehmigt|genehmigung|*erholung|aufatmen|*plus|"
     "profitabel|profitable|konjunkturpaket|stimulus|einig*|einigung|agreement|deal reached|entschärf*|"
     "lands|secures?|sichert sich|investiert|invests?|upbeat|beflügel*|treibt|treiben|rückenwind|tailwinds?|comeback|"
     "feiern|feiert|glänz*|aufholjagd|rebound|zuversicht*|optimis*|confident|gestärkt|bessert|verbessert|improves?|"
     "upside|outperforms?|beats|surpasses|tops|milliardenauftrag|deal|übernimmt|acquires?", 1),
    ("*rekord|*kursfeuerwerk|*durchbruch|*boom|record|blowout|soars", 1.5),
    ("abstürz*|stürzt ab|*rutsch|*einbruch|*absturz|*crash|*ausverkauf|*talfahrt|*kurssturz|sell-?off|crash(es)?|plunge", -1.5),
    # Geschäft gut
    ("*wachstum|wächst|wachsen|growth|grows?|*gewinnsprung|*auftrag|*bestellung|contract|orders?|"
     "partnerschaft|kooperation|partnership|expands?|expansion|überzeugt|überholt|profitiert|robust|"
     "starke|starken|starkem|starker|strong|stronger|strength|lifts?|wins?|gewinnt|erfolgreich|successful|"
     "turnaround|verdient|innovation|demand lifts|nachfrage steigt", 1),
    # Geschäft schlecht
    ("*verlust|loss(es)?|*klage|lawsuit|sued|*ermittl|investigation|probe|*razzia|*skandal|scandal|*affäre|affair|"
     "*betrug|fraud|*pleite|*insolvenz|bankruptcy|*streik|strikes?|walkout|*rückruf|ruft \\S+ zurück|recalls?|"
     "*lieferproblem|*engpass|*engpässe|shortages?|*mangel|*störung|outage|*hacker|cyberattack|*datenleck|breach|"
     "*warnung|warnt|warnen|warns?|warning|*sorge|sorgen|*angst|fears?|concerns?|worries|*blase|bubble|"
     "schwach|schwache|schwachem|schwachen|schwacher|*schwäche|weak|weaker|weakness|enttäusch\\w*|disappoint\\w*|"
     "kämpft|kämpfen|struggles?|leidet|bremst|bremsen|drückt|drücken|droht|drohen|threats?|threatens?|"
     "schaden|schadet|schädigt|hurts?|damage|*spionage|attackiert|*strafe|bußgeld|fined?|antitrust|*kartell|"
     "*sanktion|zölle|*zoll|tariffs?|*rezession|recession|flop|scheitert|gescheitert|fails?|failed|"
     "*rechtskosten|kreditausfälle|bad loans|*unfall|crash test|fragen auf|*panne|probleme|problems?|"
     "kassiert|unter beschuss|*abbau|penalty|penalties|zittern|zittert|nervös|nervosität|jitters|"
     "abschreib*|write-?downs?|writes? down|impairment|*rückschlag|setbacks?|ärger|trouble|fürcht*|befürcht*|"
     "verbrenn*|*gegenwind|headwinds?|schwächel*|verschärf*|stalls?|stagniert|oversupply|*unsicherheit|uncertainty|"
     "verunsicher*|*belastung|brechen ein|einbrechen|verschuld*|*schulden|debt|downgrade|*kritik|criticism|kritisier*|"
     "protest*|boykott*|boycott|*verbot|ban|bans|banned|verklagt|*eklat|*chaos|*desaster|disaster|*pleiten|"
     "verlangsamt|*ausfall|*kündigung|downturn|*flaute|*krise|crisis|*risiko|risks?|verzögerung\\w*|delay(s|ed)?", -1),
]

NEGATORS = {"nicht", "kein", "keine", "keinen", "keiner", "not", "no", "never", "ohne", "without", "nie"}
INTENSIFIERS = {"kräftig", "kräftige", "kräftigen", "deutlich", "deutliche", "deutlichen", "massiv", "massive", "massiven",
                "stark", "heftig", "heftige", "sharply", "strongly", "steep", "steeply", "unerwartet", "dramatisch", "massively",
                "überraschend", "sprunghaft", "drastisch", "big", "huge", "hart"}
MODALS = re.compile(r"\b(könnte|könnten|dürfte|dürften|could|might|may|would|soll angeblich|wohl)\b")
SUBORDINATE = re.compile(r"\b(trotz|despite|obwohl|although|even as|in spite of)\b")
CONTRAST = re.compile(r"(?:,\s*|\s)(aber|doch|jedoch|allerdings|but|yet|however)\s")


def _split_top(pattern: str) -> list[str]:
    """An „|“ trennen, aber nicht innerhalb von Klammern."""
    parts, depth, cur = [], 0, ""
    for ch in pattern:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


def _compile_words(entries):
    """„*stamm“ = auch mitten im Wort (Zusammensetzungen), „stamm*“ = Wortanfang mit beliebiger Endung."""
    out = []
    for pattern, w in entries:
        parts = []
        for alt in _split_top(pattern):
            if alt.startswith("*"):
                parts.append(rf"[\wäöüß-]*{alt[1:].rstrip('*')}[\wäöüß]*")
            elif alt.endswith("*"):
                parts.append(rf"\b{alt[:-1]}[\wäöüß]*")
            else:
                parts.append(rf"\b{alt}\b")
        out.append((re.compile("|".join(parts)), w))
    return out


_NEUTRAL = [re.compile(rf"\b(?:{p})") for p in NEUTRAL]
_CLICKBAIT = re.compile("|".join(rf"\b(?:{p})" for p in CLICKBAIT))
_PHRASES = [(re.compile(rf"\b(?:{p})"), w) for p, w in PHRASES]
_WORDS = _compile_words(WORDS)


def normalize(text: str) -> str:
    t = (text or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("„", '"')
    return " ".join(t.split())


def _multipliers(t: str) -> list[float]:
    """Gewicht je Zeichen: Nebensatz mit „trotz“ 0,3, Teil vor „aber/but“ 0,7, sonst 1."""
    mult = [1.0] * len(t)
    for m in CONTRAST.finditer(t):
        for i in range(0, m.start()):
            mult[i] = min(mult[i], 0.7)
    for m in SUBORDINATE.finditer(t):
        end = re.search(r"[,;:.!?–]\s|\s[-–]\s", t[m.end():])
        stop = m.end() + end.start() if end else len(t)
        if stop == len(t) and m.start() > 0:
            # „… trotz X“ am Satzende: nur die nächsten zwei Wörter gehören zum Nebensatz
            words = list(re.finditer(r"\S+", t[m.end():]))[:2]
            stop = m.end() + (words[-1].end() if words else 0)
        for i in range(m.start(), stop):
            mult[i] = 0.3
    return mult


def explain(text: str) -> tuple[float, list[tuple[str, float]]]:
    """Wert und die einzelnen Treffer (für Tests und zum Nachvollziehen)."""
    t = normalize(text)
    if not t:
        return 0.0, []
    head = t.split(". ", 1)[0]
    question = head.rstrip().endswith("?")
    used = [False] * len(t)
    mult = _multipliers(t)
    modal = 0.8 if MODALS.search(head) else 1.0
    hits: list[tuple[str, float]] = []

    def free(m) -> bool:
        return not any(used[m.start():m.end()])

    def take(m, w: float):
        for i in range(m.start(), m.end()):
            used[i] = True
        if not w:
            return
        before = re.findall(r"[\wäöüß']+", t[max(0, m.start() - 30):m.start()])[-3:]
        after = re.findall(r"[\wäöüß']+", t[m.end():m.end() + 20])[:1]
        if any(b in NEGATORS for b in before):
            w = -w
        if any(b in INTENSIFIERS for b in before[-2:] + after):
            w *= 1.5
        # Treffer in der Schlagzeile zählen voll, in der Zusammenfassung zu 60 %
        w *= mult[m.start()] * (1.0 if m.start() < len(head) else 0.6)
        hits.append((m.group(0), round(w, 2)))

    for rx in _NEUTRAL:
        for m in rx.finditer(t):
            if free(m):
                take(m, 0)
    for rx, w in _PHRASES:
        for m in rx.finditer(t):
            if free(m):
                take(m, w)
    for rx, w in _WORDS:
        for m in rx.finditer(t):
            if free(m):
                take(m, w)
    if not hits:
        return 0.0, []
    bait = 0.3 if _CLICKBAIT.search(head) else 1.0
    total = sum(w for _, w in hits) * modal * (0.7 if question else 1.0) * bait
    weight = sum(abs(w) for _, w in hits)
    return round(max(-1.0, min(1.0, total / (weight + 1.2))), 3), hits


def score(text: str) -> float:
    return explain(text)[0]
