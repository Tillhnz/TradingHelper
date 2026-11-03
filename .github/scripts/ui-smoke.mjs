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

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror ${page.url()}: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console ${page.url()}: ${m.text()}`); });
await page.goto(`${base}/login`);
await page.evaluate((t) => localStorage.setItem("tradehelper_token", t), token);

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

const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
await mobile.goto(`${base}/login`);
await mobile.evaluate((t) => localStorage.setItem("tradehelper_token", t), token);
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
const before = await mobile.evaluate(() => window.scrollY);
const box = await mobile.locator(".chart-main").boundingBox();
if (box) {
  await mobile.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
  await mobile.mouse.wheel(0, 400);
  await mobile.waitForTimeout(800);
}
console.log("scroll over locked chart", before, "->", await mobile.evaluate(() => window.scrollY));
await mobile.goto(`${base}/watchlist`);
await mobile.waitForTimeout(9000);
await mobile.screenshot({ path: "shots/mobile-watchlist.png", fullPage: true });

console.log("ERRORS", JSON.stringify(errors, null, 2));
await browser.close();
