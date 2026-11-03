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

for (const s of ["AAPL", "SAP.DE", "BTC-EUR"]) console.log("watchlist", s, JSON.stringify(await api("/watchlist", { symbol: s })).slice(0, 160));
const q = await api("/quote/AAPL");
const buyDate = new Date(Date.now() - 120 * 86400000).toISOString().slice(0, 10);
if (q.price) {
  console.log("position", JSON.stringify(await api("/positions", { symbol: "AAPL", quantity: 10, buy_price: Math.round(q.price * 0.93), buy_date: buyDate, stop: Math.round(q.price * 0.85), target: Math.round(q.price * 1.15) })).slice(0, 200));
  console.log("position2", JSON.stringify(await api("/positions", { symbol: "SAP.DE", quantity: 5, buy_price: 300, buy_date: buyDate, stop: 250 })).slice(0, 200));
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror ${page.url()}: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console ${page.url()}: ${m.text()}`); });
await page.goto(`${base}/login`);
await page.evaluate((t) => localStorage.setItem("tradehelper_token", t), token);

for (const [path, name, wait] of [["/", "home", 9000], ["/watchlist", "watchlist", 7000], ["/chart/AAPL", "chart", 9000], ["/depot", "depot", 9000], ["/settings", "settings", 3000]]) {
  await page.goto(base + path);
  await page.waitForTimeout(wait);
  await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
}
await page.goto(`${base}/chart/AAPL`);
await page.waitForTimeout(8000);
await page.screenshot({ path: "shots/chart-top.png" });
await page.getByRole("button", { name: "Kauf erfassen" }).first().click();
await page.waitForTimeout(2500);
await page.screenshot({ path: "shots/buy-dialog.png" });

const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
await mobile.goto(`${base}/login`);
await mobile.evaluate((t) => localStorage.setItem("tradehelper_token", t), token);
await mobile.goto(`${base}/depot`);
await mobile.waitForTimeout(8000);
await mobile.screenshot({ path: "shots/mobile-depot.png", fullPage: true });

console.log("ERRORS", JSON.stringify(errors, null, 2));
await browser.close();
