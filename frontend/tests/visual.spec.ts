import { expect, test } from "@playwright/test";

test("capture desktop, dark, and mobile layouts", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.screenshot({ path: testInfo.outputPath("login.png") });
  await page.getByRole("button", { name: "Alex", exact: true }).click();
  await page.getByLabel("Verification code").fill("123456");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Open Maya Chen", exact: true }).click();
  await expect(page.locator(".message-text").first()).toBeVisible();
  await expect(page.locator(".composer-area")).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath("desktop.png") });
  await page.getByRole("button", { name: "Toggle dark mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: testInfo.outputPath("dark.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".composer-area")).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath("mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
