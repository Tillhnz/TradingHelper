// Rauchtest der Oberfläche mit echten Kursen: meldet JavaScript-Fehler und macht Screenshots (Artefakt "screenshots").
import { createHmac } from "node:crypto";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const base = "http://localhost:8080";
mkdirSync("shots", { recursive: true });
const json = (r) => r.json().catch(() => ({}));

let token = (await json(await fetch(`${base}/api/auth/setup`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ci", password: "geheim123" }) }))).token;
if (!token) token = (await json(await fetch(`${base}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ci", password: "geheim123" }) }))).token;
// Zwei-Faktor-Anmeldung ist Pflicht: einrichten (Code wie eine Authenticator-App berechnen)
function totp(secret) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "")) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const step = Buffer.alloc(8);
  step.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = createHmac("sha1", key).update(step).digest();
  const o = h[h.length - 1] & 15;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1000000).padStart(6, "0");
}
const auth = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
const s2 = await json(await fetch(`${base}/api/auth/2fa/setup`, { method: "POST", headers: auth, body: "{}" }));
const en = await json(await fetch(`${base}/api/auth/2fa/enable`, { method: "POST", headers: auth, body: JSON.stringify({ pending: s2.pending, code: totp(s2.secret), remember: true }) }));
const device = en.device;
console.log("2fa", !!s2.qr_svg, en.recovery_codes?.length, !!device);
const H = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
const api = (path, body) => fetch(`${base}/api${path}`, body ? { method: "POST", headers: H, body: JSON.stringify(body) } : { headers: H }).then(json);

console.log("search", JSON.stringify((await api("/search?q=SAP")).slice(0, 3)).slice(0, 400));
for (const s of ["DE0007164600.GTX", "IE00B4L5Y983.GTX", "AAPL", "BTC-EUR"]) console.log("watchlist", s, JSON.stringify(await api("/watchlist", { symbol: s })).slice(0, 220));
const g = await api("/history/DE0007164600.GTX?period=1y&interval=1d");
console.log("gettex history", g.rows?.length, JSON.stringify(g.rows?.slice(-1)), g.delay_min, g.as_of, g.name);
const q = await api("/quote/AAPL");
const buyDate = new Date(Date.now() - 120 * 86400000).toISOString().slice(0, 10);
if (q.price) {
  console.log("position", JSON.stringify(await api("/positions", { symbol: "AAPL", quantity: 10, buy_price: Math.round(q.price * 0.93), buy_date: buyDate, stop: Math.round(q.price * 0.85), target: Math.round(q.price * 1.15) })).slice(0, 200));
  const today = new Date().toISOString().slice(0, 10);
  const etf = await api("/quote/IE00B4L5Y983.GTX");
  console.log("position3", JSON.stringify(await api("/positions", { symbol: "IE00B4L5Y983.GTX", quantity: 50, buy_price: etf.price, buy_date: today, stop: Math.round(etf.price * 0.95 * 100) / 100, target: Math.round(etf.price * 1.12 * 100) / 100 })).slice(0, 160));
  console.log("position2", JSON.stringify(await api("/positions", { symbol: "DE0007164600.GTX", quantity: 5, buy_price: 230, buy_date: buyDate, stop: 190 })).slice(0, 200));
}

// alert-name-check: Alarm auf gettex-Wert auslösen und prüfen, dass Name statt ISIN im Verlauf steht
console.log("alert add", JSON.stringify(await api("/alerts", { symbol: "DE0007164600.GTX", kind: "price_above", params: { value: 1 }, once: true })).slice(0, 120));
console.log("alert check", JSON.stringify(await api("/alerts/check?send=false", {})).slice(0, 300));
console.log("alert log", JSON.stringify((await api("/alerts/log?limit=3"))[0]).slice(0, 300));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror ${page.url()}: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console ${page.url()}: ${m.text()}`); });
page.on("requestfailed", (r) => console.log("requestfailed", r.method(), r.url(), r.failure()?.errorText));
await page.goto(`${base}/login`);
await page.screenshot({ path: "shots/login.png" });
await page.evaluate(([t, d]) => { localStorage.setItem("tradehelper_token", t); localStorage.setItem("tradehelper_device", d || ""); }, [token, device]);
// Neuerungen-Fenster beim ersten Öffnen: fotografieren und schließen
await page.goto(`${base}/`);
await page.waitForTimeout(4000);
await page.screenshot({ path: "shots/whatsnew.png" });
if (await page.getByRole("button", { name: "Alles klar" }).count()) await page.getByRole("button", { name: "Alles klar" }).click();
const seenVersion = await page.evaluate(() => localStorage.getItem("tradehelper_seen_version"));
console.log("whatsnew seen", seenVersion);

for (const [path, name, wait] of [["/", "home", 12000], ["/portfolio", "portfolio", 6000], ["/markt", "markt", 5000],
  ["/modell", "modell", 3000], ["/watchlist", "watchlist", 9000], ["/chart/DE0007164600.GTX", "chart", 9000], ["/depot", "depot", 9000], ["/settings", "settings", 3000]]) {
  await page.goto(base + path);
  await page.waitForTimeout(wait);
  await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
}
await page.evaluate(() => localStorage.setItem("tradehelper_theme", "dark"));
await page.goto(`${base}/`);
await page.waitForTimeout(5000);
await page.screenshot({ path: "shots/home-dark.png", fullPage: true });
await page.evaluate(() => localStorage.setItem("tradehelper_theme", "light"));
await page.goto(`${base}/chart/AAPL`);
await page.waitForTimeout(8000);
await page.screenshot({ path: "shots/chart-top.png" });
await page.getByRole("button", { name: "Profi" }).first().click();
await page.waitForTimeout(5000);
await page.screenshot({ path: "shots/chart-pro.png" });
await page.getByRole("button", { name: "Einfach" }).first().click();
// Tagesverlauf (gettex aus Einzelgeschäften) und Chartart
await page.goto(`${base}/chart/DE0007164600.GTX`);
await page.waitForTimeout(7000);
await page.locator(".range-seg").getByRole("button", { name: "Tag", exact: true }).click();
await page.waitForTimeout(6000);
await page.screenshot({ path: "shots/chart-intraday.png" });
console.log("intraday", JSON.stringify(await page.evaluate(() => ({
  fresh: document.querySelector(".stock-quote p")?.textContent, price: document.querySelector(".big-price")?.textContent,
  error: document.querySelector(".chart-panel .error")?.textContent,
}))));
// kleiner Chart: nur Kursverlauf, keine Schalter für Signale/Kerzen mehr
console.log("small chart controls", await page.locator(".chart-panel select[aria-label='Darstellung'], .chart-panel input[type=checkbox]").count());
await page.locator(".range-seg").getByRole("button", { name: "Woche", exact: true }).click();
await page.waitForTimeout(6000);
await page.screenshot({ path: "shots/chart-week.png" });
const q1 = await page.evaluate(async (t) => (await fetch("/api/quotes?symbols=DE0007164600.GTX,AAPL,BTC-EUR", { headers: { Authorization: `Bearer ${t}` } })).json(), token);
console.log("quotes", JSON.stringify(q1));
await page.goto(`${base}/`);
await page.locator(".gsearch input").fill("Allianz");
await page.waitForTimeout(4000);
await page.screenshot({ path: "shots/search.png" });
await page.goto(`${base}/chart/IE00B4L5Y983.GTX`);
await page.waitForTimeout(8000);
await page.locator(".stock-actions-top .btn.primary").click();
await page.waitForTimeout(2500);
await page.getByLabel("Stückzahl").fill("10");
await page.waitForTimeout(800);
await page.screenshot({ path: "shots/buy-dialog.png" });
// Schnellkauf speichern und die Kaufbox ansehen
await page.getByRole("button", { name: /Kauf eintragen/ }).click();
await page.waitForTimeout(6000);
await page.screenshot({ path: "shots/chart-box.png" });
await page.locator(".range-seg").getByRole("button", { name: "Tag", exact: true }).click();
await page.waitForTimeout(6000);
await page.screenshot({ path: "shots/chart-box-intraday.png" });
console.log("quick buy", JSON.stringify(((await api("/positions")).items || []).filter((p) => p.symbol === "IE00B4L5Y983.GTX").map((p) => [p.buy_date, p.buy_time, p.buy_price])));
await page.goto(`${base}/chart/AAPL`);
await page.waitForTimeout(8000);
await page.screenshot({ path: "shots/chart-box-aapl.png" });
// Warum läuft der Kurs so? (Markt/Branche/Eigenes, stärkste Tage mit Schlagzeilen)
await page.locator("#warum").scrollIntoViewIfNeeded();
await page.locator("#warum .why-total, #warum .muted").first().waitFor({ timeout: 30000 }).catch(() => {});
await page.waitForTimeout(8000);
console.log("warum", (await page.locator("#warum").innerText()).replace(/\s+/g, " ").slice(0, 700));
await page.locator("#warum").screenshot({ path: "shots/warum-aapl.png" }).catch(() => {});
// Neue Zeiträume im kleinen Chart, großer Chart mit Zeitraum + Auflösung
for (const r of ["Monat", "3 Jahre", "Gesamt"]) {
  await page.locator(".range-seg").getByRole("button", { name: r, exact: true }).click();
  await page.waitForTimeout(4000);
  console.log("range", r, await page.locator(".chart-panel .error").allInnerTexts(), await page.locator(".chart-panel canvas").count());
}
await page.screenshot({ path: "shots/chart-gesamt.png" });
await page.goto(`${base}/charts/AAPL`);
await page.waitForTimeout(6000);
await page.locator(".range-seg").getByRole("button", { name: "Woche", exact: true }).click();
await page.waitForTimeout(3000);
console.log("ws resolutions Woche", JSON.stringify(await page.locator(".res-ctl button").allInnerTexts()));
await page.getByRole("button", { name: "5m", exact: true }).click();
await page.waitForTimeout(5000);
await page.screenshot({ path: "shots/workspace-week-5m.png" });

// Schattendepot: starten, handeln, Rückblick rechnen
await page.goto(`${base}/depot/schatten`);
await page.waitForTimeout(3000);
await page.screenshot({ path: "shots/shadow-empty.png", fullPage: true });
await page.getByRole("button", { name: /starten$/ }).first().click();
await page.waitForTimeout(25000);
await page.getByRole("button", { name: "Rückblick starten" }).click();
const t0 = Date.now();
while (Date.now() - t0 < 300000) {
  await page.waitForTimeout(5000);
  if (await page.locator(".verdict-box").count()) break;
  if (await page.locator(".error").count()) break;
}
console.log("shadow orders", JSON.stringify((await api("/paper")).orders?.slice(0, 5)));
console.log("backtest seconds", Math.round((Date.now() - t0) / 1000));
console.log("shadow", JSON.stringify(await page.evaluate(() => ({
  stats: [...document.querySelectorAll(".stat")].map((e) => e.textContent),
  verdict: document.querySelector(".verdict-box")?.textContent,
  rows: [...document.querySelectorAll("#rueckblick tbody tr")].map((r) => r.textContent),
  orders: document.querySelectorAll("main .table-wrap")[1]?.textContent?.slice(0, 600),
  error: document.querySelector(".error")?.textContent,
}))));
await page.screenshot({ path: "shots/shadow.png", fullPage: true });

const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
await mobile.goto(`${base}/login`);
await mobile.evaluate(([t, v]) => { localStorage.setItem("tradehelper_token", t); localStorage.setItem("tradehelper_seen_version", v); }, [token, seenVersion]);
await mobile.goto(`${base}/depot`);
await mobile.waitForTimeout(8000);
await mobile.screenshot({ path: "shots/mobile-depot.png", fullPage: true });
await mobile.goto(`${base}/chart/IE00B4L5Y983.GTX`);
await mobile.waitForTimeout(9000);
await mobile.screenshot({ path: "shots/mobile-etf-today.png", fullPage: true });
await mobile.getByRole("button", { name: "Profi" }).first().click();
await mobile.waitForTimeout(5000);
await mobile.locator(".chart-panel").screenshot({ path: "shots/mobile-etf-pro-chart.png" });
for (const iv of ["1 Minute", "1 Sekunde", "2 Stunden"]) {
  const b = mobile.locator(`.chart-panel button[title="${iv}"]`);
  if (!(await b.count())) { console.log("no interval button", iv); continue; }
  await b.click();
  await mobile.waitForTimeout(4000);
  const err = await mobile.locator(".chart-panel .error").count();
  console.log("interval", iv, "error", err, await mobile.locator(".chart-panel .error").first().textContent().catch(() => ""));
  await mobile.locator(".chart-panel").screenshot({ path: `shots/mobile-etf-${iv.replace(/ /g, "")}.png` });
}
await mobile.getByRole("button", { name: "Einfach" }).first().click();
await mobile.goto(`${base}/chart/DE0007164600.GTX`);
await mobile.waitForTimeout(9000);
await mobile.screenshot({ path: "shots/mobile-stock.png", fullPage: true });
const mBlocks = mobile.locator(".panel.blocks");
if (await mBlocks.count()) { await mBlocks.scrollIntoViewIfNeeded(); await mBlocks.screenshot({ path: "shots/mobile-blocks.png" }); }
console.log("stock news", JSON.stringify(await mobile.evaluate(() => [...document.querySelectorAll(".news-list li")].slice(0, 8).map((li) => li.querySelector(".news-src")?.textContent + " | " + li.querySelector(".news-head")?.textContent))));
const before = await mobile.evaluate(() => window.scrollY);
const box = await mobile.locator(".chart-main").boundingBox();
if (box) {
  await mobile.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
  await mobile.mouse.wheel(0, 400);
  await mobile.waitForTimeout(800);
}
console.log("scroll over locked chart", before, "->", await mobile.evaluate(() => window.scrollY));
await mobile.goto(`${base}/depot/schatten`);
await mobile.waitForTimeout(6000);
await mobile.screenshot({ path: "shots/mobile-shadow.png", fullPage: true });
await mobile.goto(`${base}/watchlist`);
await mobile.waitForTimeout(9000);
await mobile.screenshot({ path: "shots/mobile-watchlist.png", fullPage: true });
await mobile.goto(`${base}/`);
await mobile.waitForTimeout(12000);
await mobile.screenshot({ path: "shots/mobile-home.png", fullPage: true });
const mNews = mobile.locator(".news-grid");
if (await mNews.count()) { await mNews.scrollIntoViewIfNeeded(); await mobile.screenshot({ path: "shots/mobile-news.png" }); }

// Laptop (1366×768) und Tablet (1024×768)
for (const [w, h, tag] of [[1366, 768, "laptop"], [1024, 768, "tablet"]]) {
  const pg = await browser.newPage({ viewport: { width: w, height: h } });
  pg.on("pageerror", (e) => errors.push(`pageerror ${tag}: ${e.message}`));
  await pg.goto(`${base}/login`);
  await pg.evaluate(([t, v]) => { localStorage.setItem("tradehelper_token", t); localStorage.setItem("tradehelper_seen_version", v); }, [token, seenVersion]);
  await pg.goto(`${base}/chart/IE00B4L5Y983.GTX`);
  await pg.waitForTimeout(9000);
  await pg.screenshot({ path: `shots/${tag}-stock.png` });
  const boPanel = pg.locator(".panel.breakout");
  if (await boPanel.count()) await boPanel.screenshot({ path: `shots/${tag}-breakout.png` });
  else console.log("no breakout panel for", tag);
  const co = pg.locator(".panel.company");
  if (await co.count()) { await co.scrollIntoViewIfNeeded(); await pg.waitForTimeout(1500); await co.screenshot({ path: `shots/${tag}-company.png` }); }
  else console.log("no company panel for", tag);
  const moodBtn = pg.locator(".news-list .mood-tag.as-btn").first();
  if (await moodBtn.count()) {
    await moodBtn.scrollIntoViewIfNeeded();
    await moodBtn.click();
    await pg.waitForTimeout(300);
    await pg.locator(".news-list").first().screenshot({ path: `shots/${tag}-mood-fix.png` });
    await pg.locator(".mood-fix .mood-tag.neg").first().click();
    await pg.waitForTimeout(1500);
    console.log("mood fixed", tag, await pg.locator(".news-list li").first().locator(".mood-tag").first().textContent());
  } else console.log("no news for", tag);
  const blocks = pg.locator(".panel.blocks");
  if (await blocks.count()) { await blocks.scrollIntoViewIfNeeded(); await blocks.screenshot({ path: `shots/${tag}-blocks.png` }); }
  await pg.locator(".stock-head .btn-sell").first().click();
  await pg.waitForTimeout(1200);
  await pg.screenshot({ path: `shots/${tag}-sell-dialog.png` });
  const onTop = await pg.evaluate(() => {
    const m = document.querySelector(".modal");
    if (!m) return "kein Dialog";
    const r = m.getBoundingClientRect();
    const pts = [[0.25, 0.3], [0.75, 0.3], [0.5, 0.5], [0.25, 0.7], [0.75, 0.7]];
    return pts.every(([x, y]) => m.contains(document.elementFromPoint(r.left + r.width * x, r.top + r.height * y))) ? "oben" : "verdeckt";
  });
  console.log(`${tag} sell dialog layer`, onTop);
  await pg.keyboard.press("Escape");
  const before = await pg.evaluate(() => window.scrollY);
  const box = await pg.locator(".chart-main").boundingBox();
  if (box) { await pg.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await pg.mouse.wheel(0, 500); await pg.waitForTimeout(800); }
  console.log(`${tag} wheel over chart scrolls page`, before, "->", await pg.evaluate(() => window.scrollY));
  await pg.goto(`${base}/`);
  await pg.waitForTimeout(10000);
  await pg.screenshot({ path: `shots/${tag}-home.png` });
  console.log(`${tag} news`, JSON.stringify(await pg.evaluate(() => ({
    mine: document.querySelector('[aria-label="Nachrichten zu deinen Werten"] .news-list')?.children.length ?? 0,
    market: document.querySelector('[aria-label="Marktnachrichten"] .news-list')?.children.length ?? 0,
    stocks: [...document.querySelectorAll(".news-stock")].slice(0, 6).map((e) => e.textContent),
    sources: [...document.querySelectorAll('[aria-label="Marktnachrichten"] .news-src')].slice(0, 8).map((e) => e.textContent),
  }))));
  const newsBox = pg.locator(".news-grid");
  if (await newsBox.count()) await newsBox.screenshot({ path: `shots/${tag}-news.png` });
  await pg.keyboard.press("/");
  console.log(`${tag} slash focuses search`, await pg.evaluate(() => document.activeElement?.getAttribute("aria-label")));
  await pg.close();
}

// Chart-Arbeitsplatz: Linie setzen, Trendlinie, RSI dazu
await page.goto(`${base}/charts/DE0007164600.GTX`);
await page.waitForTimeout(7000);
await page.getByRole("button", { name: /Waagrechte Linie/ }).click();
const wsBox = await page.locator(".ws-main").boundingBox();
await page.mouse.click(wsBox.x + wsBox.width * 0.6, wsBox.y + wsBox.height * 0.35);
await page.waitForTimeout(500);
await page.getByRole("button", { name: /Trendlinie/ }).click();
await page.mouse.click(wsBox.x + wsBox.width * 0.2, wsBox.y + wsBox.height * 0.75);
await page.waitForTimeout(400);
console.log("trend after 1st click", await page.locator(".ws-help").textContent().catch(() => "-"));
await page.mouse.click(wsBox.x + wsBox.width * 0.7, wsBox.y + wsBox.height * 0.45);
await page.waitForTimeout(400);
console.log("trend after 2nd click", await page.locator(".ws-help").textContent().catch(() => "-"), await page.locator(".ws-list li").count());
await page.getByRole("button", { name: /Fibonacci/ }).click();
await page.mouse.click(wsBox.x + wsBox.width * 0.3, wsBox.y + wsBox.height * 0.8);
await page.mouse.click(wsBox.x + wsBox.width * 0.85, wsBox.y + wsBox.height * 0.2);
// Strahl in einem Zug ziehen (so zeichnet man auf dem Handy)
await page.getByRole("button", { name: /Strahl/ }).click();
await page.mouse.move(wsBox.x + wsBox.width * 0.25, wsBox.y + wsBox.height * 0.7);
await page.mouse.down();
await page.mouse.move(wsBox.x + wsBox.width * 0.45, wsBox.y + wsBox.height * 0.55, { steps: 8 });
await page.mouse.move(wsBox.x + wsBox.width * 0.6, wsBox.y + wsBox.height * 0.4, { steps: 8 });
await page.mouse.up();
await page.waitForTimeout(400);
console.log("ray by drag", await page.locator(".ws-list li").count(), await page.locator(".ws-selbar").count());
await page.getByLabel("Kennlinie hinzufügen").selectOption("rsi");
await page.getByRole("button", { name: /Bewegen/ }).click();
await page.waitForTimeout(2500);
await page.screenshot({ path: "shots/workspace.png", fullPage: true });
const layout = await api("/charts/DE0007164600.GTX");
console.log("workspace layout", JSON.stringify({ drawings: layout.drawings?.map((d) => d.kind), indicators: layout.indicators?.map((i) => i.kind) }));
await page.goto(`${base}/charts`);
await page.waitForTimeout(2500);
await page.screenshot({ path: "shots/charts-picker.png" });

// Morgenbericht: verschicken (Test-Topic) und als Pop-up öffnen
const putSettings = (body) => fetch(`${base}/api/settings`, { method: "PUT", headers: H, body: JSON.stringify(body) }).then(json);
await putSettings({ ntfy_topic: `th-ci-${Date.now()}`, app_url: "http://tradehelper.test" });
console.log("report send", JSON.stringify(await api("/report/send", {})));
await page.goto(`${base}/?bericht=latest`);
await page.waitForTimeout(3000);
await page.goto(`${base}/`);
await page.waitForTimeout(6000);
await page.getByRole("button", { name: "Bericht", exact: true }).click();
await page.waitForTimeout(2500);
await page.screenshot({ path: "shots/report-modal.png" });
console.log("report modal", JSON.stringify(await page.evaluate(() => ({
  title: document.querySelector(".modal h2")?.textContent, items: document.querySelectorAll(".report-item").length,
}))));
await page.keyboard.press("Escape");

// Startseite anpassen: Bausteine bearbeiten, Mini-Chart hinzufügen, Beträge verbergen
await page.getByRole("button", { name: "Anpassen" }).click();
await page.waitForTimeout(800);
await page.screenshot({ path: "shots/home-edit.png" });
await page.getByRole("button", { name: "Nachrichten zu deinen Werten entfernen" }).click();
await page.getByRole("button", { name: "Baustein", exact: false }).first().click();
await page.waitForTimeout(500);
await page.screenshot({ path: "shots/home-gallery.png" });
await page.getByRole("button", { name: /Mini-Chart/ }).click();
await page.getByLabel("Wert suchen").fill("SAP");
await page.waitForTimeout(4000);
await page.locator(".modal").getByRole("button", { name: "Hinzufügen", exact: true }).first().click();
await page.getByRole("checkbox", { name: "Beträge verbergen" }).check();
await page.getByRole("button", { name: /Fertig/ }).click();
await page.waitForTimeout(4000);
console.log("home layout", JSON.stringify(await page.evaluate(() => ({
  widgets: [...document.querySelectorAll(".wgrid > .w .wtitle, .wgrid > .w .home-greet")].map((x) => x.textContent),
}))));
await page.screenshot({ path: "shots/home-private.png", fullPage: true });

// Beträge über das Auge am Vermögen wieder zeigen, Reihenfolge „A–Z“ und die neue Analyse
await page.getByRole("button", { name: "Beträge anzeigen" }).first().click().catch((e) => console.log("eye", e.message));
await page.waitForTimeout(1500);
await page.goto(`${base}/watchlist`);
await page.getByRole("button", { name: "A–Z" }).click();
await page.waitForTimeout(1500);
console.log("sorted", JSON.stringify(await page.evaluate(() => [...document.querySelectorAll(".asset-list .asset-name, .asset-list strong")].slice(0, 6).map((x) => x.textContent))));
await page.screenshot({ path: "shots/watchlist-sorted.png", fullPage: true });
console.log("strategy", JSON.stringify(await api("/strategy?budget=8")).slice(0, 900));
await page.goto(`${base}/analyse`);
await page.waitForTimeout(9000);
await page.screenshot({ path: "shots/analyse.png", fullPage: true });

// PDF-Upload im Depot-Dialog (kleine Abrechnung und eine große Datei, wie Bank-PDFs mit Logos)
{
  const fs = await import("node:fs");
  const small = fs.readFileSync(".github/fixtures/abrechnung-kauf.pdf");
  const big = Buffer.concat([small, Buffer.from("\n%" + "x".repeat(4_000_000) + "\n")]);
  fs.writeFileSync("/tmp/abrechnung-gross.pdf", big);
  await page.goto(`${base}/portfolio`);
  await page.getByRole("button", { name: /Depot hinzufügen/ }).first().click();
  await page.getByRole("button", { name: /Anderer Broker/ }).click();
  await page.getByRole("button", { name: "Anlegen und Dateien wählen" }).click();
  await page.getByRole("dialog", { name: /Hochladen/ }).waitFor({ timeout: 45000 }).catch(() => {});
  console.log("nach Anlegen:", (await page.locator(".modal").first().innerText()).replace(/\s+/g, " ").slice(-200));
  await page.screenshot({ path: "shots/depot-anlegen.png" });
  for (const file of [".github/fixtures/abrechnung-kauf.pdf", "/tmp/abrechnung-gross.pdf"]) {
    const t0 = Date.now();
    await page.locator(".modal input[type=file]").setInputFiles(file);
    await page.locator(".modal").getByText(/neue Käufe\/Verkäufe erkannt|schon importiert|Fehler|nicht erreichbar|antwortet/).first()
      .waitFor({ timeout: 60000 }).catch(() => {});
    const txt = (await page.locator(".modal").innerText()).replace(/\s+/g, " ").slice(0, 300);
    console.log("pdf upload", file, `${Date.now() - t0} ms`, txt);
    await page.screenshot({ path: `shots/pdf-upload-${file.includes("gross") ? "gross" : "klein"}.png` });
    if (!/erkannt/.test(txt)) throw new Error(`PDF-Upload fehlgeschlagen: ${txt}`);
    // zurück zur Dateiauswahl für die nächste Datei
    await page.locator(".modal").getByRole("button", { name: /Andere Dateien|Zurück|Abbrechen/ }).first().click().catch(() => {});
    if (!(await page.locator(".modal input[type=file]").count())) {
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: /Hochladen|Dateien hochladen/ }).first().click().catch(() => {});
    }
  }
  await page.keyboard.press("Escape");
}

// Unternehmensdaten einer Aktie (SAP)
console.log("fundamentals SAP", JSON.stringify(await api("/fundamentals/DE0007164600.GTX")).slice(0, 600));

// Einladung: Link in der Administration erstellen, zweiten Nutzer anlegen, getrennte Daten prüfen
await page.goto(`${base}/admin`);
await page.waitForTimeout(2500);
await page.getByLabel(/Für wen/).fill("Anna");
await page.getByRole("button", { name: "Einladungslink erstellen" }).click();
await page.waitForTimeout(1500);
const inviteUrl = (await page.locator(".invite-link code").textContent()).trim();
await page.screenshot({ path: "shots/admin-users.png", fullPage: true });
console.log("invite", inviteUrl.replace(/[^/]+$/, "…"));
const ctx2 = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
await ctx2.addInitScript((v) => { try { localStorage.setItem("tradehelper_seen_version", v); } catch { /* egal */ } }, seenVersion);
const anna = await ctx2.newPage();
anna.on("pageerror", (e) => errors.push(`pageerror anna ${anna.url()}: ${e.message}`));
await anna.goto(inviteUrl);
await anna.waitForTimeout(2000);
await anna.screenshot({ path: "shots/mobile-register.png" });
await anna.getByLabel("Benutzername").fill("anna");
await anna.getByLabel(/^Passwort/).first().fill("annas-pass1");
await anna.getByLabel("Passwort wiederholen").fill("annas-pass1");
await anna.getByRole("button", { name: "Konto anlegen" }).click();
await anna.waitForTimeout(5000);
await anna.screenshot({ path: "shots/mobile-anna-home.png", fullPage: true });
await anna.goto(`${base}/watchlist`);
await anna.waitForTimeout(3000);
console.log("anna", JSON.stringify(await anna.evaluate(async () => {
  const t = localStorage.getItem("tradehelper_token");
  const get = (p) => fetch(`/api${p}`, { headers: { Authorization: `Bearer ${t}` } }).then((r) => r.json().then((j) => [r.status, j]));
  return { me: await get("/me"), watchlist: (await get("/watchlist"))[1], admin: (await get("/admin/status"))[0],
    adminLink: !!document.querySelector('a[href="/admin"]') };
})));
await anna.goto(`${base}/settings`);
await anna.waitForTimeout(2500);
await anna.screenshot({ path: "shots/mobile-anna-settings.png", fullPage: true });
await ctx2.close();

console.log("ERRORS", JSON.stringify(errors, null, 2));
await browser.close();
