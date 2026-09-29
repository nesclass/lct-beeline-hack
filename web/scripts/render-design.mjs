import { chromium } from 'playwright-core';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
const root = new URL('../../backups/docs/design/', import.meta.url).pathname;   // node web/scripts/render-design.mjs
const types = { '.html': 'text/html', '.js': 'text/javascript', '.svg': 'image/svg+xml' };
const srv = createServer(async (q, r) => { const p = join(root, decodeURIComponent(q.url.split("?")[0])); let d; try { d = await readFile(p); } catch { r.writeHead(404); return r.end(); } r.writeHead(200, { "content-type": types[extname(p)] || "application/octet-stream" }); r.end(d); }).listen(8765);
const b = await chromium.launch({ channel: 'chrome' });
const pg = await b.newPage({ viewport: { width: 1600, height: 1000 } });
pg.on('pageerror', e => console.log('ERR', e.message));
await pg.goto('http://127.0.0.1:8765/DispatcherFlow.dc.html', { waitUntil: 'networkidle' });
await pg.waitForTimeout(4000);
const ids = await pg.$$eval('[data-screen-label]', els => els.map(e => e.id));
console.log(ids);
for (const id of ids) { const el = await pg.$(`[id="${id}"]`); await el.screenshot({ path: `${root}screens/${id}.png` }); }
await b.close(); srv.close();
