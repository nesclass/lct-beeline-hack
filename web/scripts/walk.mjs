// node web/scripts/walk.mjs [normal peak short-staffed]   (APP_URL, по умолчанию http://127.0.0.1:8001)
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const base = process.env.APP_URL || 'http://127.0.0.1:8001';
const out = new URL('../../out/screens/', import.meta.url).pathname;
const scenarios = process.argv.slice(2).length ? process.argv.slice(2) : ['normal', 'peak', 'short-staffed'];
mkdirSync(out, { recursive: true });
writeFileSync(`${out}sessions.txt`, '');
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
try {
  for (const scn of scenarios) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on('console', m => { if (m.type() === 'error' && !/basemaps|tile\.|arcgisonline/.test(m.location()?.url || '')) errors.push(`${scn}: ${m.text()}`); });
    page.on('pageerror', e => errors.push(`${scn}: ${e}`));
    const shot = n => page.screenshot({ path: `${out}walk-${scn}-${n}.png`, fullPage: true });
    const step = async (name, fn, allow = null) => {
      const before = errors.length;
      try { await fn(); } catch (e) { await shot(`FAIL-${name}`); throw new Error(`${scn} / ${name}: ${e.message}`); }
      if (allow) errors.splice(before, errors.length - before, ...errors.slice(before).filter(x => !allow.test(x)));
      if (errors.length) throw new Error(`${scn} / ${name}: ошибки консоли:\n${errors.join('\n')}`);
      console.log(`  ${scn} · ${name}`);
    };
    const clock = async t => {
      const f = page.locator('input[aria-label="Часы сессии"]');
      if (!(await f.count())) await page.click('.clock-value');
      await page.fill('input[aria-label="Часы сессии"]', t);
      await page.press('input[aria-label="Часы сессии"]', 'Enter');
      // ответ сервера пришёл: часы показывают новое время или отказ (плашка «занят» на быстрых действиях не видна)
      await page.waitForFunction(v => document.querySelector('button.clock-value')?.textContent.trim() === v
                                      || document.querySelector('.band.err'), t);
    };

    await step('4a сценарий', async () => {
      await page.goto(base + '/');
      await page.waitForSelector(`.scenario-card[data-scenario="${scn}"]`);
      await shot('4a');
      await page.click(`.scenario-card[data-scenario="${scn}"] button`);
      await page.waitForURL(/\/setup$/);
    });
    const sid = page.url().match(/\/s\/([0-9a-f]+)\//)[1];
    appendFileSync(`${out}sessions.txt`, `${base}/s/${sid}/plan\n`);
    await step('4b настройка', async () => {
      await page.click('.goal >> nth=2');
      await page.fill('input[type=range]', '3');
      await shot('4b');
      await page.click('button.build');
      await page.waitForURL(/\/setup\/variants$/, { timeout: 90000 });
      await page.waitForSelector('.variant-row');
    });
    await step('4c варианты', async () => { await shot('4c'); await page.click('button.approve'); await page.waitForURL(/\/plan$/); });
    await step('4d план', async () => { await page.waitForSelector('.gantt .bar-work'); await page.hover('.gantt .bar-work >> nth=3'); await shot('4d'); });
    await step('4e заявка', async () => { await page.click('.gantt .bar-work >> nth=3'); await page.waitForSelector('.request-card'); await shot('4e'); });
    await step('4f ассистент', async () => { await page.click('button.discuss'); await page.waitForSelector('.ai-bubble'); await shot('4f'); });
    await step('4g карта', async () => { await page.click('.seg2 a:has-text("Карта")'); await page.waitForSelector('.stop'); await shot('4g'); });
    await step('4h срочная', async () => {
      await clock('13:30');
      await page.click('button.add-event');
      await page.fill('input[name=address]', 'Царицыно, ул. Луганская, 7');
      await page.waitForSelector('.preview-ok, .preview-none');
      await shot('4h');
      await page.click('button.submit-event');
      await page.waitForSelector('button.queue .badge:has-text("1")');
    });
    await step('4i–4j уход', async () => {
      await clock('13:45');
      await page.click('.tabs a:has-text("Инженеры")');
      await page.click('.eng-row >> nth=0');
      await shot('4i');
      await page.click('button.availability');
      await page.fill('.modal input[name=leave]', '14:00');
      await page.press('.modal input[name=leave]', 'Enter');
      await page.waitForSelector('.consequences');
      await shot('4j');
      await page.click('button.submit-availability');
      await page.waitForSelector('button.queue .badge:has-text("2")');
    });
    await step('4k очередь', async () => { await page.click('button.queue'); await page.waitForSelector('.changes-panel'); await shot('4k'); });
    await step('4l разбор', async () => {
      await page.click('button.replan-now');
      await page.waitForSelector('.diff-panel', { timeout: 90000 });
      await shot('4l');
    });
    await step('откат и снова', async () => {
      await page.click('button.rollback');
      await page.waitForSelector('.changes-panel');
      await page.click('button.replan-now');
      await page.waitForSelector('.diff-panel', { timeout: 90000 });
      await page.click('button.accept');
      await page.waitForSelector('.band.ok');
    });
    await step('часы назад нельзя', async () => {
      await clock('09:00');
      await page.waitForSelector('.band.err:has-text("перепланировано")');
    }, /409/);
    await step('4m аналитика', async () => { await page.click('.tabs a:has-text("Аналитика")'); await page.waitForSelector('.hour-bar'); await shot('4m'); });
    await step('заявки', async () => { await page.click('.tabs a:has-text("Заявки")'); await page.waitForSelector('.req-row'); await shot('requests'); });
    await page.close();
  }
} finally {
  await browser.close();
}
console.log('walk ok');
