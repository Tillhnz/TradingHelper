import { useEffect, useState } from "react";
import { api } from "../api.js";
import { num, pct, tone } from "../fmt.js";
import Icon from "./Icon.jsx";
import Term from "./Term.jsx";

const SYM = { EUR: "€", USD: "$", GBP: "£", CHF: "CHF" };

/** Große Beträge lesbar: 243,3 Mrd. € */
export function big(v, ccy = "EUR") {
  if (v == null) return "–";
  const a = Math.abs(v);
  const [n, unit] = a >= 1e12 ? [v / 1e12, "Bio."] : a >= 1e9 ? [v / 1e9, "Mrd."] : a >= 1e6 ? [v / 1e6, "Mio."] : [v, ""];
  return `${num(n, a >= 1e6 ? 1 : 0)}${unit ? ` ${unit}` : ""} ${SYM[ccy] || ccy || ""}`.trim();
}
const date = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join(".") : "–");
const p1 = (v) => (v == null ? "–" : `${num(v, 1)} %`);

function stockStats(f, d) {
  const c = d.currency;
  const y = d.year ? ` ${d.year}` : "";
  return [
    { k: "market_cap", label: "Börsenwert", term: "Börsenwert", value: big(f.market_cap, c), key: true },
    { k: "pe", label: `KGV${y}`, term: "KGV", value: num(f.pe, 1), key: true },
    { k: "pe_est", label: `KGV ${d.est_year || ""}e`.trim(), term: "KGV", value: num(f.pe_est, 1) },
    { k: "div_yield", label: "Dividendenrendite", term: "Dividendenrendite", value: p1(f.div_yield), key: true },
    { k: "revenue", label: `Umsatz${y}`, value: big(f.revenue, c), key: true },
    { k: "revenue_growth", label: "Umsatzwachstum", value: pct(f.revenue_growth, 1), tone: tone(f.revenue_growth), key: true },
    { k: "net_income", label: `Gewinn${y}`, value: big(f.net_income, c), tone: tone(f.net_income) },
    { k: "net_margin", label: "Nettomarge", term: "Nettomarge", value: p1(f.net_margin), key: true },
    { k: "ebit_margin", label: "EBIT-Marge", term: "EBIT-Marge", value: p1(f.ebit_margin) },
    { k: "roe", label: "Eigenkapitalrendite", term: "Eigenkapitalrendite", value: p1(f.roe) },
    { k: "equity_ratio", label: "Eigenkapitalquote", term: "Eigenkapitalquote", value: p1(f.equity_ratio) },
    { k: "eps", label: "Gewinn je Aktie", value: f.eps != null ? `${num(f.eps, 2)} ${SYM[c] || c}` : "–" },
    { k: "eps_est", label: `Gewinn je Aktie ${d.est_year || ""}e`.trim(), value: f.eps_est != null ? `${num(f.eps_est, 2)} ${SYM[c] || c}` : "–" },
    { k: "dps", label: "Dividende je Aktie", value: f.dps != null ? `${num(f.dps, 2)} ${SYM[c] || c}` : "–" },
    { k: "ex_dividend", label: "Letzter Ex-Tag", value: date(f.ex_dividend) },
    { k: "pb", label: "KBV", term: "KBV", value: num(f.pb, 1) },
    { k: "peg", label: "PEG", term: "PEG", value: num(f.peg, 2) },
    { k: "beta", label: "Beta", value: num(f.beta, 2) },
    { k: "employees", label: "Mitarbeiter", value: f.employees != null ? num(f.employees, 0) : "–" },
    { k: "free_float", label: "Streubesitz", value: p1(f.free_float) },
  ].filter((s) => f[s.k] != null);
}

function fundStats(f) {
  return [
    { k: "ter", label: "Kosten (TER)", term: "TER", value: f.ter != null ? `${num(f.ter, 2)} % p. a.` : "–", key: true },
    { k: "volume", label: "Fondsvolumen", value: big(f.volume, "EUR"), key: true },
    { k: "distribution", label: "Erträge", term: f.distribution, value: f.distribution, key: true },
    { k: "perf_1y", label: "1 Jahr", value: pct(f.perf_1y, 1), tone: tone(f.perf_1y), key: true },
    { k: "perf_3y", label: "3 Jahre", value: pct(f.perf_3y, 1), tone: tone(f.perf_3y), key: true },
    { k: "perf_5y", label: "5 Jahre", value: pct(f.perf_5y, 1), tone: tone(f.perf_5y), key: true },
    { k: "benchmark", label: "Index", value: f.benchmark },
    { k: "region", label: "Region", value: f.region },
    { k: "replication", label: "Nachbildung", value: f.replication },
    { k: "inception", label: "Aufgelegt", value: date(f.inception) },
    { k: "domicile", label: "Fondssitz", value: f.domicile },
    { k: "volatility_1y", label: "Schwankung 1 J.", value: p1(f.volatility_1y) },
    { k: "max_drawdown_1y", label: "Max. Verlust 1 J.", term: "Max. Verlust", value: pct(f.max_drawdown_1y, 1), tone: "neg" },
    { k: "risk_class", label: "Risikoklasse", term: "Risikoklasse", value: f.risk_class != null ? `${f.risk_class} von 7` : "–" },
    { k: "morningstar", label: "Morningstar", value: f.morningstar ? "★".repeat(f.morningstar) + "☆".repeat(5 - f.morningstar) : "–" },
  ].filter((s) => f[s.k] != null);
}

function Bars({ items, title, icon }) {
  if (!items?.length) return null;
  const max = Math.max(...items.map((i) => i.pct || 0)) || 1;
  return (
    <div className="co-bars">
      <h3 className="sub-title"><Icon name={icon} /> {title}</h3>
      <ul>
        {items.map((i) => (
          <li key={i.name}>
            <span className="co-bar-name">{i.name}</span>
            <span className="co-bar-track"><span style={{ width: `${(i.pct / max) * 100}%` }} /></span>
            <span className="co-bar-pct">{num(i.pct, 1)} %</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Unternehmen bzw. Fonds: Kurzbeschreibung, wichtigste Kennzahlen, bei Fonds die größten Positionen. */
export default function CompanyPanel({ symbol, pro }) {
  const [d, setD] = useState(null);
  const [all, setAll] = useState(false);
  const [long, setLong] = useState(false);

  useEffect(() => {
    let alive = true;
    setD(null);
    api.get(`/fundamentals/${encodeURIComponent(symbol)}`).then((r) => alive && setD(r)).catch(() => alive && setD({ kind: null }));
    return () => { alive = false; };
  }, [symbol]);

  if (!d) {
    return (
      <section className="panel company" aria-busy="true">
        <div className="panel-head"><h2><Icon name="building" className="h-icon" /> Unternehmen</h2></div>
        <div className="skeleton" /><div className="skeleton short" />
      </section>
    );
  }
  if (!d.kind || (!d.description && !Object.keys(d.figures || {}).length)) return null;
  const fund = d.kind === "fund";
  const stats = fund ? fundStats(d.figures || {}) : stockStats(d.figures || {}, d);
  const shown = all || pro ? stats : stats.filter((s) => s.key);
  const tags = fund ? [d.issuer, d.type, d.figures?.focus] : [d.sector, d.industry, d.country];
  const desc = d.description;

  return (
    <section className="panel company" aria-labelledby="co-h">
      <div className="panel-head">
        <h2 id="co-h"><Icon name={fund ? "pie" : "building"} className="h-icon" /> {fund ? "Über den Fonds" : "Unternehmen"}</h2>
        {d.year && !fund && <span className="muted small">Geschäftsjahr {d.year}</span>}
      </div>
      {tags.some(Boolean) && <div className="co-tags">{[...new Set(tags.filter(Boolean))].map((t) => <span key={t} className="chip">{t}</span>)}</div>}
      {desc?.tagline && <p className="co-tagline">{desc.tagline}</p>}
      {desc?.text && (
        <div className={`co-desc ${long ? "open" : ""}`}>
          <p>{desc.text}</p>
          <p className="muted small co-src">
            {desc.text.length > 260 && <button className="link small" onClick={() => setLong((x) => !x)}>{long ? "Weniger" : "Weiterlesen"}</button>}
            <span>Quelle: {desc.url ? <a href={desc.url} target="_blank" rel="noreferrer noopener">{desc.source} <Icon name="link" /></a> : desc.source}</span>
          </p>
        </div>
      )}
      {shown.length > 0 && (
        <div className="stats co-stats">
          {shown.map((s) => (
            <div key={s.k} className={`stat ${s.tone || ""}`}>
              <span className="stat-label">{s.term ? <Term name={s.term}>{s.label}</Term> : s.label}</span>
              <strong className="stat-value">{s.value}</strong>
            </div>
          ))}
        </div>
      )}
      {!pro && stats.length > shown.length && (
        <button className="toggle-link" onClick={() => setAll(true)}>Alle {stats.length} Kennzahlen</button>
      )}
      {fund && (
        <div className="co-lists">
          <Bars items={d.holdings} title="Größte Positionen" icon="list" />
          <Bars items={d.branches} title="Branchen" icon="pie" />
        </div>
      )}
      <p className="muted small co-foot">Kennzahlen: {d.figures_source}{!fund && d.est_year ? ` · „e“ = Schätzung der Analysten` : ""}</p>
    </section>
  );
}
