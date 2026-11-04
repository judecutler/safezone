// Drives every SafeZone flow in a phone-sized Chromium against a running server.
// Usage: node tools/verify_e2e.cjs <screenshot-dir> [base-url]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const OUT = process.argv[2], BASE = process.argv[3] ?? 'http://127.0.0.1:8000';
const PHOTO = path.join(__dirname, '..', 'demo', 'living_room.jpg');
const errors = [];
const check = (ok, msg) => { if (!ok) { errors.push(msg); console.log('FAIL', msg); } else console.log('ok', msg); };

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const scan = await (await fetch(`${BASE}/api/scan?name=Bedroom`, {
    method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: fs.readFileSync(PHOTO) })).json();
  const expectHazards = scan.classified.filter((c) => c.role === 'hazard').length;
  const expectSpots = scan.spots.filter((s) => s.kind !== 'no_cover').length;
  const demo = await (await fetch(`${BASE}/api/demo`)).json();
  const expectShelters = demo.plan.shelters.matches.length;
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    permissions: ['geolocation'], geolocation: { longitude: -122.5099, latitude: 37.7699, accuracy: 12 },
  });
  const page = await ctx.newPage();
  page.on('console', (m) => m.type() === 'error' && !m.text().includes('ERR_INTERNET_DISCONNECTED') && errors.push('console: ' + m.text()));
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  const shot = (name, full = false) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: full });

  await page.goto(BASE + '/');
  await page.waitForSelector('.hero');
  await shot('01-start');

  await page.click('text=Start my plan');
  await page.click('text=Use the demo address');
  await page.click('button[type=submit]');
  await page.waitForSelector('.building');
  check(await page.locator('.flag.tone-alert').count() === 1, 'tsunami flag shows as alert');
  check(await page.locator('.building .tag-sample').count() > 0, 'sample building is tagged');
  await shot('02-address', true);

  await page.click('text=Next: household');
  for (const n of ['Young children', 'Wheelchair or mobility aid', 'Pets']) await page.click(`text=${n}`);
  await page.waitForFunction(() => document.querySelectorAll('.need[aria-pressed=true]').length === 3).catch(() => {});
  check(await page.locator('.need[aria-pressed=true]').count() === 3, 'three needs pressed');
  await shot('03-household');

  await page.click('text=Next: rooms');
  await page.fill('#room-name', 'Bedroom');
  await page.setInputFiles('#room-photo', PHOTO);
  await page.waitForSelector('.scanning');
  await page.waitForTimeout(400);
  await shot('04-scanning');
  await page.waitForSelector('.room .overlay');
  check(await page.locator('.room .ov-balloon').count() === expectHazards, `${expectHazards} hazard balloons`);
  check(await page.locator('.room .ov-relation').count() === scan.relations.length, `${scan.relations.length} relation connectors`);
  check(await page.locator('.room .ov-spot').count() === expectSpots, `${expectSpots} crosshair(s); no_cover draws none`);
  check((await page.textContent('.room')).includes('What Muse Spark noticed'), 'relations attributed to Muse Spark');
  await page.locator('.fix label').first().click();
  await page.waitForSelector('.fix.is-done').catch(() => {});
  check(await page.locator('.fix.is-done').count() === 1, 'fix ticked');
  await page.evaluate(() => scrollTo(0, 0));
  await shot('05-room', true);

  await page.click('text=Build my plan');
  await page.waitForSelector('.titleblock');
  check(await page.locator('.fix.is-done').count() === 1, 'ticked fix carried into the plan');
  await page.waitForTimeout(300);
  await shot('06-plan', true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await shot('06b-plan-desktop', true);
  await page.setViewportSize({ width: 390, height: 844 });

  await page.emulateMedia({ media: 'print' });
  await shot('07-print', true);
  await page.pdf({ path: `${OUT}/07-fridge-sheet-letter.pdf`, format: 'Letter', printBackground: true });
  await page.pdf({ path: `${OUT}/07-fridge-sheet-a4.pdf`, format: 'A4', printBackground: true });
  await page.emulateMedia({ media: 'screen' });

  await page.reload();
  await page.waitForSelector('.titleblock');
  check(await page.locator('.fix.is-done').count() === 1, 'plan and fix state survive reload');

  await page.click('.btn-emergency');
  await page.waitForSelector('.em-dch');
  check(await page.locator('.em-shaking a, .em-shaking .routemap').count() === 0, 'shaking screen shows no route');
  await shot('08-shaking');
  await page.click('text=Shaking has stopped');
  await page.waitForSelector('.routemap');
  await page.waitForFunction(() => document.querySelector('.rm-pos')?.getAttribute('visibility') === 'visible');
  check(true, 'live position dot visible');
  await shot('09-route', true);
  await page.click('text=Shelters that fit your household');
  await page.waitForSelector('.shelter');
  check(await page.locator('.shelter').count() === expectShelters, `${expectShelters} shelters`);
  check(await page.locator('.tag-replay').count() === expectShelters, 'replay label on every card');
  await shot('10-shelters', true);

  const sw = await page.evaluate(async () => !!(await navigator.serviceWorker.ready).active);
  check(sw, 'service worker active');
  await ctx.setOffline(true);
  await page.goto(BASE + '/?screen=emergency');
  await page.waitForSelector('.em-dch');
  check((await page.textContent('.em-spots')).includes('Bedroom'), 'offline shaking screen shows the saved safe spot');
  await shot('11-offline-shaking');
  await page.click('text=Shaking has stopped');
  await page.waitForSelector('.routemap');
  await shot('12-offline-route', true);
  await page.click('text=Shelters that fit your household');
  await page.waitForSelector('.shelter');
  await page.click('.em-exit');
  await page.waitForSelector('.titleblock');
  await page.waitForFunction(() => [...document.querySelectorAll('.overlay image')].every((i) => i.getAttribute('href')?.startsWith('blob:')));
  check(true, 'offline plan page shows room photos from IndexedDB');
  await shot('13-offline-plan');
  await ctx.setOffline(false);

  const ctx2 = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const p2 = await ctx2.newPage();
  p2.on('pageerror', (e) => errors.push('pageerror(demo): ' + e.message));
  await p2.goto(BASE + '/');
  await p2.click('text=Load the demo household');
  await p2.waitForSelector('.titleblock');
  check(await p2.locator('.overlay image[href^="blob:"]').count() === 1, 'demo room photo stored locally');
  await p2.screenshot({ path: `${OUT}/14-demo-plan.png` });

  const ctx3 = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const p3 = await ctx3.newPage();
  p3.on('pageerror', (e) => errors.push('pageerror(outside): ' + e.message));
  await p3.goto(BASE + '/?screen=emergency');
  await p3.waitForSelector('.em-dch');
  check((await p3.textContent('main')).includes('No saved plan on this device'), 'emergency with no plan says so');
  await p3.click('text=Shaking has stopped');
  await p3.waitForSelector('.em-calm');
  check(await p3.locator('.routemap').count() === 0, 'no plan, no route drawn');
  await p3.screenshot({ path: `${OUT}/15-no-plan-after.png` });
  await p3.click('.em-exit');
  await p3.click('text=Start my plan');
  await p3.fill('#address', '1 Dr Carlton B Goodlett Pl, San Francisco, CA 94102');
  await p3.click('button[type=submit]');
  await p3.waitForSelector('.building');
  await p3.click('text=Next: household');
  await p3.click('text=Next: rooms');
  await p3.setInputFiles('#room-photo', PHOTO);
  await p3.waitForSelector('.room .overlay');
  await p3.click('text=Build my plan');
  await p3.waitForSelector('.titleblock');
  await p3.click('.btn-emergency');
  await p3.click('text=Shaking has stopped');
  await p3.waitForSelector('.em-calm');
  const txt = await p3.textContent('main');
  check(txt.includes('outside the mapped tsunami hazard area') && !txt.includes('Go now'), 'outside the zone: stay-put text, no go-now');
  check(await p3.locator('.routemap').count() === 0, 'outside the zone: no route');
  await p3.screenshot({ path: `${OUT}/16-outside-after.png`, fullPage: true });
  await browser.close();
  console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'ALL CHECKS PASSED');
  process.exit(errors.length ? 1 : 0);
})();
