// Скриншот страницы и проверка консоли в системном Chrome.
//   node web/scripts/shot.mjs <url> <out.png> [--wait css] [--click css] [--fill css=value] [--hover css]
// Ширина окна — SHOT_WIDTH (по умолчанию 1440, как в макетах). Код 1 — были ошибки консоли.
// Ошибки загрузки тайлов карты не считаются: они зависят от сети.
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { chromium } from 'playwright-core';

const [url, out, ...steps] = process.argv.slice(2);
if (!url || !out) { console.error('usage: shot.mjs <url> <out.png> [--wait css] [--click css] [--fill css=value] [--hover css]'); process.exit(2); }
mkdirSync(dirname(out), { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: +(process.env.SHOT_WIDTH || 1440), height: 900 } });
const errors = [];
page.on('console', m => { if (m.type() === 'error' && !/basemaps|tile\.|arcgisonline/.test(m.location()?.url || '')) errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
await page.goto(url, { waitUntil: 'networkidle' });
for (let i = 0; i < steps.length; i += 2) {
  const [k, v] = [steps[i], steps[i + 1]];
  if (k === '--wait') await page.waitForSelector(v, { timeout: 60000 });
  else if (k === '--click') { await page.click(v); await page.waitForLoadState('networkidle'); }
  else if (k === '--hover') await page.hover(v);
  else if (k === '--fill') {
    // селектор может быть атрибутным (input[name=address]) — тогда разделитель это "="
    // сразу после закрывающей "]", а не первое "=" в строке (оно внутри селектора).
    const brk = v.lastIndexOf(']');
    const j = brk !== -1 && v[brk + 1] === '=' ? brk + 1 : v.indexOf('=');
    await page.fill(v.slice(0, j), v.slice(j + 1));
  }
}
await page.screenshot({ path: out, fullPage: true });
await browser.close();
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
console.log(`ok ${out}`);
