// One-off manual Playwright smoke test (not part of a test suite) for the
// customer-facing complaint flow (submit -> reference number -> status
// lookup). Run with: node e2e-complaint-flow.mjs
import { chromium } from "@playwright/test";

const BASE = "http://localhost:5173";

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  console.log("1. Opening /submit-complaint...");
  await page.goto(`${BASE}/submit-complaint`, { waitUntil: "networkidle" });
  await page.waitForSelector("h1");
  console.log("   Heading:", await page.textContent("h1"));

  console.log("2. Filling and submitting the complaint form...");
  const inputs = page.locator(".login-card input");
  await inputs.nth(0).fill("Priya Sharma");
  await inputs.nth(1).fill("priya.sharma@example.com");
  await page.fill(
    "textarea",
    "I was charged a hidden annual maintenance fee on my savings account that was never disclosed when I opened it, and support has not responded to my emails for ten days.",
  );

  const submitResponse = page.waitForResponse(
    (res) => res.url().includes("/complaints") && res.request().method() === "POST",
  );
  await page.click('button[type="submit"]');
  const resp = await submitResponse;
  console.log("   POST /complaints ->", resp.status());

  await page.waitForSelector(".reference-id", { timeout: 10000 });
  const reference = (await page.textContent(".reference-id"))?.trim();
  console.log("   Reference number:", reference);
  await page.screenshot({ path: "e2e-complaint-01-submitted.png", fullPage: true });

  console.log("3. Clicking through to status page...");
  await page.click('button:has-text("Check status now")');
  await page.waitForURL(`${BASE}/complaint-status/${reference}`);
  await page.waitForSelector(".pill");
  console.log("   Status pills:", await page.locator(".pill").allTextContents());
  await page.screenshot({ path: "e2e-complaint-02-status.png", fullPage: true });

  console.log("4. Testing manual lookup form at /complaint-status...");
  await page.goto(`${BASE}/complaint-status`, { waitUntil: "networkidle" });
  await page.fill("input", reference ?? "");
  const lookupResponse = page.waitForResponse(
    (res) => res.url().includes(`/complaints/${reference}`) && res.request().method() === "GET",
  );
  await page.click('button[type="submit"]');
  await lookupResponse;
  await page.waitForSelector(".pill");
  console.log("   Manual lookup OK, pills:", await page.locator(".pill").allTextContents());

  console.log("5. Checking /login has customer links...");
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  console.log("   Links on login page:", await page.locator("a").allTextContents());

  console.log("\nConsole/page errors captured during the run:", consoleErrors.length);
  consoleErrors.forEach((e) => console.log("  -", e));

  await browser.close();
  console.log("\nDone.");
})();
