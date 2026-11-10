import { expect, test, type Page } from "@playwright/test";

const unique = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
async function login(page: Page, account = "Alex") {
  page.on("pageerror", error => console.log("BROWSER ERROR", error.stack));
  await page.goto("/");
  await page.getByRole("button", { name: account, exact: true }).click();
  await page.getByLabel("Verification code").fill("123456");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Conversation list")).toBeVisible();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
}
async function send(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Message", exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".message-text").filter({ hasText: text })).toHaveCount(1);
}

test("login, refresh, logout, and keyboard search", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await login(page);
  await page.getByRole("button", { name: "Open Maya Chen", exact: true }).click();
  await page.reload();
  await expect(page.getByLabel("Conversation list")).toBeVisible();
  await page.keyboard.press("Control+k");
  await expect(page.getByLabel("Search conversations and contacts")).toBeFocused();
  await page.getByLabel("Search conversations and contacts").fill("maya");
  await expect(page.getByRole("button", { name: "Open Maya Chen", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Priya Shah", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Good to see you." })).toBeVisible();
  expect(errors).toEqual([]);
});

test("two users exchange messages, typing, receipts, unread state, and reconnect", async ({ browser }) => {
  const a = await browser.newContext(), b = await browser.newContext();
  const alex = await a.newPage(), maya = await b.newPage();
  try {
    await login(alex); await login(maya, "Maya");
    await alex.getByRole("button", { name: "Open Maya Chen", exact: true }).click();
    await maya.getByRole("button", { name: "Open Alex Morgan", exact: true }).click();
    await alex.getByRole("textbox", { name: "Message", exact: true }).fill("Typing a thought");
    await expect(maya.getByLabel("Someone is typing")).toBeVisible();
    const message = `Browser message ${unique()}`;
    await send(alex, message);
    await expect(maya.locator(".message-text").filter({ hasText: message })).toHaveCount(1);
    await maya.bringToFront(); await maya.getByRole("textbox", { name: "Message", exact: true }).focus();
    await expect(alex.locator(".message-row").filter({ hasText: message }).getByLabel("Read", { exact: true })).toBeVisible();
    await maya.getByRole("button", { name: "Open The reading room", exact: true }).click();
    const unread = `Unread ${unique()}`;
    await send(alex, unread);
    await expect(maya.getByRole("button", { name: "Open Alex Morgan", exact: true }).locator(".unread-badge")).toBeVisible();
    await b.setOffline(true);
    const offline = `Offline recovery ${unique()}`;
    await send(alex, offline);
    await b.setOffline(false);
    await maya.getByRole("button", { name: "Open Alex Morgan", exact: true }).click();
    await expect(maya.locator(".message-text").filter({ hasText: offline })).toHaveCount(1);
    await maya.reload();
    await expect(maya.locator(".message-text").filter({ hasText: offline })).toHaveCount(1);
  } finally { await a.close(); await b.close(); }
});

test("quoted replies and reactions survive refresh", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Open Maya Chen", exact: true }).click();
  const text = `Quote me ${unique()}`;
  await send(page, text);
  const row = page.locator(".message-row").filter({ has: page.locator(".message-text", { hasText: text }) });
  await row.hover(); await row.getByRole("button", { name: "Reply to message" }).click();
  await expect(page.locator(".reply-preview")).toContainText(text);
  await send(page, `Reply ${unique()}`);
  await expect(page.locator(".quoted-message").filter({ hasText: text })).toBeVisible();
  await row.hover(); await row.getByRole("button", { name: "React to message" }).click();
  await page.getByRole("button", { name: "React 👍", exact: true }).click();
  await expect(row.getByRole("button", { name: "👍: 1 reaction", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator(".quoted-message").filter({ hasText: text })).toBeVisible();
  await expect(page.locator(".message-row").filter({ has: page.locator(".message-text", { hasText: text }) }).getByRole("button", { name: "👍: 1 reaction", exact: true })).toBeVisible();
});

test("group creation, membership changes, admin controls, and live removal", async ({ browser }) => {
  const a = await browser.newContext(), b = await browser.newContext();
  const alex = await a.newPage(), maya = await b.newPage();
  try {
    await login(alex); await login(maya, "Maya");
    const name = `Test group ${unique()}`;
    await alex.getByRole("button", { name: "New group", exact: true }).click();
    await alex.getByLabel("Group name", { exact: true }).fill(name);
    await alex.getByRole("dialog").getByRole("button", { name: /Maya Chen/ }).click();
    await alex.getByRole("button", { name: "Create group", exact: true }).click();
    await expect(maya.getByRole("button", { name: `Open ${name}`, exact: true })).toBeVisible();
    await maya.getByRole("button", { name: `Open ${name}`, exact: true }).click();
    await send(alex, `Group hello ${unique()}`);
    await maya.getByRole("button", { name: "Conversation details" }).click();
    await expect(maya.getByRole("button", { name: "Add members", exact: true })).toHaveCount(0);
    await maya.getByRole("button", { name: "Close dialog" }).click();
    await alex.getByRole("button", { name: "Conversation details" }).click();
    await alex.getByRole("button", { name: "Add members", exact: true }).click();
    await alex.locator(".person-row").filter({ hasText: "Sam Rivera" }).getByRole("button", { name: "Add", exact: true }).click();
    await alex.getByRole("button", { name: "Back to group" }).click();
    await expect(alex.getByRole("dialog").locator(".member-row")).toHaveCount(3);
    await alex.locator(".member-row").filter({ hasText: "Sam Rivera" }).getByRole("button", { name: "Make admin" }).click();
    await expect(alex.locator(".member-row").filter({ hasText: "Sam Rivera" })).toContainText("Group admin");
    alex.once("dialog", dialog => dialog.accept());
    await alex.locator(".member-row").filter({ hasText: "Maya Chen" }).getByRole("button", { name: "Remove", exact: true }).click();
    await expect(maya.getByRole("button", { name: `Open ${name}`, exact: true })).toHaveCount(0);
    await expect(maya.getByRole("textbox", { name: "Message", exact: true })).toHaveCount(0);
  } finally { await a.close(); await b.close(); }
});

test("registration, profile editing, contacts, and a new direct chat", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account", exact: true }).click();
  await page.getByLabel("Display name").fill("Browser Tester");
  await page.getByLabel(/^Username/).fill(`tester_${unique()}`);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Verification code").fill("123456");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByLabel("Conversation list")).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByLabel("Display name").fill("Updated Tester");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Profile updated.");
  await page.locator('input[type="file"]').setInputFiles({ name: "avatar.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAIAAABvFaqvAAAAIklEQVR4nGP0bbvFQA3ARBVTRg0aNWjUoFGDRg0aNYgiAAAf3QHdUa8FLwAAAABJRU5ErkJggg==", "base64") });
  await expect(page.getByRole("status")).toContainText("Profile photo updated.");
  await expect(page.locator(".settings-avatar img")).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "New message", exact: true }).first().click();
  await page.getByRole("button", { name: "Add a contact", exact: true }).click();
  await page.getByLabel(/^Username/).fill("maya");
  await page.getByRole("button", { name: "Add contact", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Maya Chen/ }).click();
  await send(page, `New account hello ${unique()}`);
});

test("dark mode persists and the mobile chat has no horizontal overflow", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Toggle dark mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Back to chats" }).click();
  await expect(page.getByLabel("Conversation list")).toBeVisible();
  await page.getByRole("button", { name: "Open Maya Chen", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
