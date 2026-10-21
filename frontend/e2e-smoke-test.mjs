// One-off manual Playwright smoke test (not part of a test suite) --
// actually drives the real app in a real headless browser against the real
// backend/DB, since no interactive browser tool is available in this
// environment. Run with: node e2e-smoke-test.mjs
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
  page.on("dialog", async (dialog) => {
    console.log(`   [ALERT DIALOG] ${dialog.type()}: ${dialog.message()}`);
    await dialog.dismiss();
  });
  page.on("response", async (res) => {
    if (res.url().startsWith("http://127.0.0.1:8010")) {
      let note = "";
      try {
        const body = await res.json();
        note = Array.isArray(body) ? `${body.length} items` : JSON.stringify(body).slice(0, 150);
      } catch {
        note = "(non-JSON or empty body)";
      }
      console.log(`   [network] ${res.request().method()} ${res.url()} -> ${res.status()} ${note}`);
    }
  });

  console.log("1. Navigating to app root (should redirect to /login)...");
  await page.goto(BASE, { waitUntil: "networkidle" });
  console.log("   URL:", page.url());
  await page.screenshot({ path: "e2e-01-login.png" });

  console.log("2. Logging in...");
  await page.fill('input[type="email"]', "admin@novapay.test");
  await page.fill('input[type="password"]', "TestPass123");
  await page.click('button[type="submit"]');
  await page.waitForURL(BASE + "/", { timeout: 5000 });
  console.log("   Logged in, now at:", page.url());

  console.log("3. Waiting for approval queue to render...");
  await page.waitForSelector("h1");
  const heading = await page.textContent("h1");
  console.log("   Heading:", heading);
  const cardCountBefore = await page.locator(".action-card").count();
  console.log("   Pending action cards rendered:", cardCountBefore);
  await page.screenshot({ path: "e2e-02-approvals.png", fullPage: true });

  if (cardCountBefore === 0) {
    console.log("   No pending actions to test approve/reject against -- skipping step 4.");
  } else {
    console.log("4. Finding the first card with an enabled Approve button...");
    const enabledApprove = page.locator(".action-card button.approve:not([disabled])").first();
    const enabledCount = await page.locator(".action-card button.approve:not([disabled])").count();
    console.log(`   ${enabledCount}/${cardCountBefore} cards have an enabled Approve button.`);

    if (enabledCount === 0) {
      console.log("   None enabled (all visible cards are legacy triage rows) -- skipping click test.");
    } else {
      const reloadResponse = page.waitForResponse(
        (res) => res.url().includes("/agent-actions?status=pending") && res.request().method() === "GET",
      );
      await enabledApprove.click();
      await reloadResponse; // wait for the actual post-approve refetch, not a guessed delay
      await page.waitForFunction(() => !document.querySelector(".centered-message")); // loading text gone
      const cardCountAfter = await page.locator(".action-card").count();
      console.log("   Pending action cards after approve:", cardCountBefore, "->", cardCountAfter);
      await page.screenshot({ path: "e2e-03-after-approve.png", fullPage: true });
    }
  }

  console.log("5. Navigating to Tickets page...");
  await page.click('a[href="/tickets"]');
  await page.waitForSelector(".data-table", { timeout: 15000 });
  const rowCount = await page.locator(".data-table tbody tr").count();
  console.log("   Ticket rows rendered:", rowCount);
  await page.screenshot({ path: "e2e-04-tickets.png", fullPage: true });

  console.log("6. Opening first ticket detail...");
  await page.click(".data-table tbody tr:first-child a");
  await page.waitForSelector(".narrative", { timeout: 15000 });
  const narrative = await page.textContent(".narrative");
  console.log("   Narrative:", narrative?.slice(0, 80));
  await page.screenshot({ path: "e2e-05-ticket-detail.png", fullPage: true });

  console.log("\nConsole/page errors captured during the run:", consoleErrors.length);
  consoleErrors.forEach((e) => console.log("  -", e));

  await browser.close();
  console.log("\nDone.");
})();
