// Records the local app in isolated Chromium. No browser chrome or sign-in pages.
import { chromium, expect } from '@playwright/test';
import { mkdir, readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { setTimeout as hold } from 'node:timers/promises';

const mode = process.argv[2];
if (!['local', 'live'].includes(mode)) throw new Error('Choose local or live.');
const baseURL = process.env.REHEARSAL_URL ?? 'http://127.0.0.1:8766';
const path = resolve(process.env.REHEARSAL_VIDEO ?? `../media/${mode}.webm`);
const brand = JSON.parse(await readFile(new URL('../brand.json', import.meta.url), 'utf-8'));
await mkdir(dirname(path), { recursive: true });

const browser = await chromium.launch();
const size = { width: 1440, height: 1000 };
const seed = await browser.newContext({ viewport: size, baseURL });
const defaultTarget = mode === 'live' ? 'databricks' : 'local';
const headings = (page, title) => page.getByRole('heading', { name: title, exact: true });
const button = (page, name) => page.getByRole('button', { name, exact: true });
const selector = (page, name) => page.getByRole('combobox', { name, exact: true });

async function select(page, label, value) {
  const control = selector(page, label);
  await control.selectOption(value);
  await expect(control).toHaveValue(value, { timeout: 8000 });
  await expect(page.getByRole('region', { name: 'Rehearsal controls' })).toHaveAttribute('aria-busy', 'false');
}
async function check(page, title) {
  await button(page, 'Run checks').click();
  await headings(page, title).waitFor({ timeout: 65000 });
}
async function ready(page) {
  await page.goto('/');
  await headings(page, 'Migration review').waitFor();
  await button(page, 'Reset').click();
  await expect(page.getByRole('region', { name: 'Rehearsal controls' })).toHaveAttribute('aria-busy', 'false');
}

try {
  const setup = await seed.newPage();
  await ready(setup);
  await select(setup, 'Target', defaultTarget);
  await check(setup, 'Switch blocked');
  await seed.close();

  const context = await browser.newContext({ viewport: size, baseURL, recordVideo: { dir: dirname(path), size } });
  const page = await context.newPage();
  const started = performance.now();
  const video = page.video();
  await page.goto('/');
  await headings(page, 'Switch blocked').waitFor();
  await page.evaluate(() => document.fonts.ready.then(() => true));

  async function caption(text, seconds, focus = '') {
    console.log(`${((performance.now() - started) / 1000).toFixed(1)}s ${text}`);
    await page.evaluate(({ text, focus, mode }) => {
      document.querySelector('#capture-caption')?.remove();
      document.querySelector('#capture-focus')?.remove();
      const band = document.createElement('aside');
      band.id = 'capture-caption';
      band.style.cssText = 'position:fixed;z-index:20;bottom:0;left:0;right:0;min-height:70px;padding:15px 46px;display:flex;align-items:center;gap:22px;background:#242b24;color:#fffefa;font:500 19px "Instrument Sans Variable",system-ui;pointer-events:none';
      const label = document.createElement('span');
      label.textContent = mode === 'live' ? 'LIVE WAREHOUSES' : 'LOCAL REHEARSAL';
      label.style.cssText = 'font:500 12px "IBM Plex Mono",monospace;color:#f1e6c9;white-space:nowrap;border:1px solid #697569;border-radius:4px;padding:7px 10px';
      const description = document.createElement('span');
      description.textContent = text;
      band.append(label, description);
      document.body.append(band);
      if (focus) {
        const target = document.querySelector(focus);
        if (!target) return;
        const rect = target.getBoundingClientRect();
        const outline = document.createElement('div');
        outline.id = 'capture-focus';
        outline.style.cssText = `position:fixed;z-index:19;left:${rect.left - 3}px;top:${rect.top - 3}px;width:${rect.width + 6}px;height:${rect.height + 6}px;border:2px solid #b18342;border-radius:8px;pointer-events:none`;
        document.body.append(outline);
      }
    }, { text, focus, mode });
    await hold(seconds * 1000);
  }

  async function switchAndRecover(provider, timings) {
    await select(page, 'Scenario', 'clean');
    await caption('Select the corrected report and run a fresh comparison on the same batch.', timings[0]);
    await check(page, 'Ready for approval');
    await caption('The checks pass. The old system keeps serving until a person approves.', timings[1], '.decision');
    await button(page, 'Switch to cloud').click();
    await headings(page, 'Switch approved').waitFor({ timeout: 65000 });
    await expect(page.locator('.served strong')).toHaveText(provider);
    await caption(`${provider} returned the approved report. The active backend is visible in the header and activity log.`,
      timings[2], '.served');
    await button(page, 'Simulate failure').click();
    await headings(page, 'Serving fallback').waitFor({ timeout: 12000 });
    await caption('A fresh DuckDB query returned the current verified batch. The timer starts when the injected failure is detected.',
      timings[3], '.decision');
  }

  try {
    await caption('January 6 shows 80,126 trips and $38,831.25 in both systems.', mode === 'live' ? 8 : 9, '.snapshot');
    await caption('The two Midtown zones are each wrong by $813. The zone check blocks the switch.', mode === 'live' ? 10 : 12, '.evidence');
    if (mode === 'local') {
      await switchAndRecover('DuckDB candidate', [4, 8, 10, 13]);
    } else {
      await page.evaluate(brand => {
        const architecture = document.createElement('section');
        architecture.id = 'capture-architecture';
        architecture.style.cssText = 'position:fixed;inset:0;z-index:18;background:#f4f3ee;color:#242620;padding:92px 110px;font:500 22px "Instrument Sans Variable",system-ui';
        const title = document.createElement('h1');
        title.textContent = brand.name + ' architecture';
        architecture.append(title);
        const blocks = [
          ['01  INPUT', 'Two verified TLC Parquet files', 'December has no CBD fee field. January preserves signed cents.'],
          ['02  COMPUTE', 'DuckDB source ↔ Databricks SQL or BigQuery', 'Each engine reads row-level records and groups by month, day, and pickup zone.'],
          ['03  DECIDE', 'FastAPI comparison and approval', 'Checks bind the provider, input fingerprints, current batch and report revision.'],
          ['04  SERVE', 'React review → active adapter → verified fallback', 'A successful cloud read enables the failure exercise. A stale source returns unavailable.'],
        ];
        for (const [label, headline, description] of blocks) {
          const row = document.createElement('div');
          row.style.cssText = 'padding:20px 0;border-bottom:1px solid #d2d3c8;display:grid;grid-template-columns:155px 1fr;gap:6px 18px';
          const key = document.createElement('small');
          key.style.cssText = 'color:#51644e;font:500 15px "IBM Plex Mono",monospace;grid-row:span 2;align-self:center';
          key.textContent = label;
          const bold = document.createElement('strong');
          bold.textContent = headline;
          const note = document.createElement('span');
          note.style.cssText = 'font-size:17px;color:#5d6055';
          note.textContent = description;
          row.append(key, bold, note);
          architecture.append(row);
        }
        document.body.append(architecture);
      }, brand);
      await caption('The public files feed independent queries. FastAPI owns approval, live routing and recovery.', 24);
      await page.evaluate(() => document.querySelector('#capture-architecture')?.remove());

      await select(page, 'Scenario', 'wrong_day');
      await check(page, 'Switch blocked');
      await caption('The month still reconciles after the wrong-day fault. January 6 and 7 differ by $38,831.25 in opposite directions.', 13, '.evidence');
      await select(page, 'Scenario', 'stale');
      await check(page, 'Switch blocked');
      await caption('A December-only candidate cannot serve the current December and January batch.', 10, '.decision');
      await switchAndRecover('Databricks SQL', [4, 10, 12, 10]);

      await button(page, 'Reset').click();
      await expect(page.getByRole('region', { name: 'Rehearsal controls' })).toHaveAttribute('aria-busy', 'false');
      await select(page, 'Target', 'bigquery');
      await check(page, 'Switch blocked');
      await caption('The same fault also blocks the live BigQuery candidate. Its data came from a separate batch load.', 8, '.evidence');
      await switchAndRecover('BigQuery', [3, 6, 9, 13]);
      const remaining = 198 - (performance.now() - started) / 1000;
      if (remaining > 0) await caption('Hold the cutover on any failed check. After a failure, serve only a verified current source batch.', remaining);
    }
  } finally {
    await context.close();
    await video.saveAs(path);
    await video.delete();
  }
} finally {
  await browser.close();
}
