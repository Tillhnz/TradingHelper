// Rauchtest der Oberfläche mit echten Kursen: meldet JavaScript-Fehler und macht Screenshots (Artefakt "screenshots").
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const base = "http://localhost:8080";
mkdirSync("shots", { recursive: true });
const json = (r) => r.json().catch(() => ({}));

let token = (await json(await fetch(`${base}/api/auth/setup`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ci", password: "geheim123" }) }))).token;
if (!token) token = (await json(await fetch(`${base}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "ci", password: "geheim123" }) }))).token;
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
await page.goto(`${base}/login`);
await page.evaluate((t) => localStorage.setItem("tradehelper_token", t), token);
// Neuerungen-Fenster beim ersten Öffnen: fotografieren und schließen
await page.goto(`${base}/`);
await page.waitForTimeout(4000);
await page.screenshot({ path: "shots/whatsnew.png" });
if (await page.getByRole("button", { name: "Alles klar" }).count()) await page.getByRole("button", { name: "Alles klar" }).click();
const seenVersion = await page.evaluate(() => localStorage.getItem("tradehelper_seen_version"));
console.log("whatsnew seen", seenVersion);

for (const [path, name, wait] of [["/", "home", 12000], ["/watchlist", "watchlist", 9000], ["/chart/DE0007164600.GTX", "chart", 9000], ["/depot", "depot", 9000], ["/settings", "settings", 3000]]) {
  await page.goto(base + path);
  await page.waitForTimeout(wait);
  await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
}
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
await page.getByRole("button", { name: "1 T", exact: true }).click();
await page.waitForTimeout(6000);
await page.screenshot({ path: "shots/chart-intraday.png" });
console.log("intraday", JSON.stringify(await page.evaluate(() => ({
  fresh: document.querySelector(".stock-quote p")?.textContent, price: document.querySelector(".big-price")?.textContent,
  error: document.querySelector(".chart-panel .error")?.textContent,
}))));
await page.getByLabel("Darstellung").selectOption("candles");
await page.waitForTimeout(2500);
await page.screenshot({ path: "shots/chart-intraday-candles.png" });
await page.getByRole("button", { name: "1 W", exact: true }).click();
await page.waitForTimeout(6000);
await page.screenshot({ path: "shots/chart-week.png" });
await page.getByLabel("Darstellung").selectOption("area");
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
await page.getByRole("button", { name: "1 T", exact: true }).click();
await page.waitForTimeout(6000);
await page.screenshot({ path: "shots/chart-box-intraday.png" });
console.log("quick buy", JSON.stringify(((await api("/positions")).items || []).filter((p) => p.symbol === "IE00B4L5Y983.GTX").map((p) => [p.buy_date, p.buy_time, p.buy_price])));
await page.goto(`${base}/chart/AAPL`);
await page.waitForTimeout(8000);
await page.screenshot({ path: "shots/chart-box-aapl.png" });

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
