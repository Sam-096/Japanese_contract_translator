import { chromium } from "playwright";
import path from "node:path";

const SCRATCH = "C:\\Users\\kotta\\AppData\\Local\\Temp\\claude\\f--janpanese-contract-translator\\a55fd09a-988c-418e-90d8-dd00a84939cb\\scratchpad";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1300, height: 1000 } });
const errors = [];
page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
page.on("pageerror", (err) => errors.push(String(err)));

const log = (msg) => console.log(`[verify] ${msg}`);

try {
  await page.goto("http://localhost:5173", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("text=Drop a Japanese contract");

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles("F:\\janpanese_contract_translator\\keiyaku.pdf");
  log("uploaded keiyaku.pdf");

  await page.waitForSelector("text=Original", { timeout: 30000 });
  await page.waitForSelector("canvas", { timeout: 30000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCRATCH, "final-original.png") });
  log("PASS: Original tab rendered a real PDF page");

  await page.waitForSelector("text=Ready", { timeout: 90000 });
  log("PASS: job completed");

  await page.getByRole("button", { name: "Translated PDF" }).click();
  await page.waitForSelector("canvas", { timeout: 30000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCRATCH, "final-translated.png") });
  log("PASS: Translated PDF tab rendered");

  await page.getByRole("button", { name: "Clause review" }).click();
  await page.waitForSelector("text=Japanese source", { timeout: 10000 });
  const reviewText = await page.locator("body").innerText();
  log(`PASS: Clause review tab works (has EN text: ${reviewText.includes("Article")})`);
  await page.screenshot({ path: path.join(SCRATCH, "final-review.png") });

  log(`console errors: ${JSON.stringify(errors)}`);
} catch (err) {
  console.error("[verify] SCRIPT ERROR:", err);
  await page.screenshot({ path: path.join(SCRATCH, "final-error.png") });
  process.exitCode = 1;
} finally {
  await browser.close();
}
