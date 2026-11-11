import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const full = process.env.REHEARSAL_BROWSER_DATA === 'full';
const screenshotDir = process.env.REHEARSAL_SCREENSHOTS;
const clouds = process.env.REHEARSAL_BROWSER_CLOUDS?.split(',') ?? [];
const fee = full ? '$38,831.25' : '$4.25';
const trips = full ? '80,126' : '6';
const delta = full ? '$813.00' : '$1.75';

async function screenshot(page: Page, name: string) {
  if (!screenshotDir) return;
  await mkdir(screenshotDir, { recursive: true });
  await page.screenshot({ path: join(screenshotDir, name + '.png'), animations: 'disabled', fullPage: true });
}

async function verifyJourney(page: Page, target: string, backend: string, shot: string) {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', entry => { if (entry.type() === 'error') errors.push(entry.text()); });
  await page.goto('/');
  const switchButton = page.getByRole('button', { name: 'Switch to cloud' });
  const decision = (title: string) => page.getByRole('heading', { name: title, exact: true });
  const backendLabel = page.getByText('Serving backend', { exact: true }).locator('..');
  const controls = page.getByRole('region', { name: 'Rehearsal controls' });
  await expect(page.getByRole('heading', { name: 'Migration review' })).toBeVisible();
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(controls).toHaveAttribute('aria-busy', 'false');
  const targetControl = page.getByRole('combobox', { name: 'Target', exact: true });
  await targetControl.selectOption(target);
  await expect(targetControl).toHaveValue(target);
  await expect(controls).toHaveAttribute('aria-busy', 'false');
  await expect(switchButton).toBeDisabled();
  await page.getByRole('button', { name: 'Run checks', exact: true }).click();
  await expect(decision('Switch blocked')).toBeVisible();
  await expect(page.getByText('Totals match', { exact: false })).toBeVisible();
  const daily = page.getByRole('region', { name: 'Daily report' });
  await expect(daily.getByText(fee, { exact: true })).toHaveCount(2);
  await expect(daily.getByText(trips, { exact: true })).toHaveCount(2);
  await expect(page.getByRole('row', { name: /Midtown Center/ })).toContainText('−' + delta);
  await expect(page.getByRole('row', { name: /Midtown East/ })).toContainText('+' + delta);
  await expect(switchButton).toBeDisabled();
  await expect(backendLabel).toContainText('DuckDB source');
  await expect(page.getByText(target === 'local' ? 'Local rehearsal' : 'Live warehouse', { exact: false })).toBeVisible();
  await screenshot(page, shot + '-blocked');

  const scenario = page.getByRole('combobox', { name: 'Scenario', exact: true });
  await scenario.selectOption('clean');
  await expect(scenario).toHaveValue('clean');
  await expect(page.getByRole('button', { name: 'Run checks', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Run checks', exact: true }).click();
  await expect(decision('Ready for approval')).toBeVisible();
  await expect(backendLabel).toContainText('DuckDB source');
  await expect(switchButton).toBeEnabled();
  await switchButton.click();
  await expect(decision('Switch approved')).toBeVisible();
  await expect(backendLabel).toContainText(backend);
  await expect(page.getByText('Active report · Jan 6, 2025')).toBeVisible();
  await expect(page.getByText(trips + ' trips · ' + fee)).toBeVisible();
  await screenshot(page, shot + '-switched');

  await page.getByRole('button', { name: 'Simulate failure', exact: true }).click();
  await expect(decision('Serving fallback')).toBeVisible();
  await expect(backendLabel).toContainText('DuckDB source');
  await expect(page.getByText(/Simulated failure · \d+\.\d{2} ms recovery/)).toBeVisible();
  await expect(page.getByText('Fallback report served', { exact: true })).toBeVisible();
  await screenshot(page, shot + '-fallback');
  expect(errors).toEqual([]);
}

test('desktop exercises the real local controls and report', async ({ page }) => {
  await verifyJourney(page, 'local', 'DuckDB candidate', 'desktop-local');
  if (process.env.REHEARSAL_EXPECT_BRAND) {
    await expect(page).toHaveTitle(process.env.REHEARSAL_EXPECT_BRAND + ' · ' + process.env.REHEARSAL_EXPECT_SUBTITLE);
    await expect(page.getByText(process.env.REHEARSAL_EXPECT_BRAND, { exact: true })).toBeVisible();
  }
});

test('mobile fits the page and can use the same workflow with keyboard focus', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Migration review' })).toBeVisible();
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Rehearsal controls' })).toHaveAttribute('aria-busy', 'false');
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Migration review' })).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('combobox', { name: 'Target', exact: true })).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await verifyJourney(page, 'local', 'DuckDB candidate', 'mobile-local');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('source failure renders an unavailable report', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.getByRole('combobox', { name: 'Scenario', exact: true }).selectOption('clean');
  await page.getByRole('button', { name: 'Run checks', exact: true }).click();
  await page.getByRole('button', { name: 'Switch to cloud' }).click();
  await page.getByRole('combobox', { name: 'Failure test', exact: true }).selectOption('stale');
  await page.getByRole('button', { name: 'Simulate failure', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Report unavailable' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Report unavailable' })).toContainText(/did not return the current verified batch/);
  await expect(page.getByText('Active report · Jan 6, 2025')).toHaveCount(0);
});

for (const [target, backend] of [['databricks', 'Databricks SQL'], ['bigquery', 'BigQuery']]) {
  test(`live ${backend} switch and recovery through browser controls`, async ({ page }) => {
    test.skip(!clouds.includes(target), 'Enable explicitly against a configured full-data server.');
    await verifyJourney(page, target, backend, target);
  });
}
