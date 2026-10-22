// Manual Playwright check of the chatbot flow against the real local app (Vite on :5173, API on :8010):
// a customer chats, a fraud report is handed over, staff reply from the inbox, the customer receives it
// without reloading, and staff resolve it. Spends a few real LLM calls and leaves one resolved conversation.
//
// Usage: node e2e-chat-flow.mjs [screenshot-dir]
import { chromium } from "playwright";

const OUT = process.argv[2] ?? ".";
const BASE = "http://localhost:5173";
const browser = await chromium.launch();
const errors = [];
const watch = (p, tag) => {
  p.on("pageerror", (e) => errors.push(`${tag}: ${e.message}`));
  p.on("console", (m) => m.type() === "error" && !m.text().includes("favicon") && errors.push(`${tag}: ${m.text()}`));
};
const check = (label, ok) => { console.log(`${ok ? "PASS" : "FAIL"}  ${label}`); if (!ok) process.exitCode = 1; };

const cust = await (await browser.newContext({ viewport: { width: 1280, height: 860 } })).newPage();
watch(cust, "customer");
await cust.goto(BASE + "/submit-complaint", { waitUntil: "networkidle" });
await cust.click(".chat-launcher");
await cust.waitForSelector(".chat-suggestions");
await cust.click(".chat-suggestions button:first-child");
await cust.waitForSelector(".chat-sources", { timeout: 30000 });
check("policy answer shows its sources", (await cust.locator(".chat-sources em").count()) > 0);

await cust.fill("#chat-input", "Someone called and I shared my OTP, Rs 8,000 was debited from my account");
await cust.keyboard.press("Enter");
await cust.waitForSelector(".chat-banner", { timeout: 30000 });
check("fraud report is handed to a person", true);

const staff = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
watch(staff, "staff");
await staff.goto(BASE + "/login");
await staff.fill('input[type="email"]', "admin@novapay.test");
await staff.fill('input[type="password"]', "TestPass123");
await staff.click('button[type="submit"]');
await staff.waitForSelector(".stat-value");
await staff.click('a[href="/conversations"]');
await staff.waitForSelector("a.inbox-item");
check("inbox lists the fraud chat as waiting", (await staff.locator("a.inbox-item .flag").first().textContent()) === "Possible fraud" && (await staff.locator(".waiting").count()) > 0);
await staff.click("a.inbox-item");
await staff.waitForSelector(".thread-summary");
check("summary and AI draft are shown", (await staff.inputValue("#staff-reply")).length > 20);
await staff.fill("#staff-reply", "Hello, this is the NovaPay support team. Please block your card now.");
await staff.click("button:has-text('Send reply')");
await staff.waitForSelector(".msg-admin");

await cust.waitForSelector(".chat-sender", { timeout: 15000 });
check("customer receives the staff reply without reloading", true);
await staff.click("button:has-text('Mark resolved')");
await cust.waitForSelector(".chat-system", { timeout: 15000 });
check("customer is told it was resolved", true);

check("no console errors", errors.length === 0);
if (errors.length) console.log(errors);
await cust.screenshot({ path: `${OUT}/e2e-chat-customer.png` });
await staff.screenshot({ path: `${OUT}/e2e-chat-staff.png` });
await browser.close();
