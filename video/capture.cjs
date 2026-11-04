// Captures real app footage for the demo video from a server running the recorded demo.
// Usage: node video/capture.cjs <outdir> [base-url]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = process.argv[2];
const BASE = process.argv[3] ?? 'http://127.0.0.1:8000';
const DEMO_COORDS = { longitude: -122.5099836, latitude: 37.7694736, accuracy: 15 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
fs.mkdirSync(OUT, { recursive: true });

async function open(browser, opts) {
  const ctx = await browser.newContext({ permissions: ['geolocation', 'camera'], geolocation: DEMO_COORDS, ...opts });
  await ctx.route(/fonts\.(googleapis|gstatic)\.com|tile\.openstreetmap\.org|disaportaldata\.gsi\.go\.jp/, (r) => r.abort());
  const page = await ctx.newPage();
  await page.addInitScript(() => { window.speechSynthesis && (window.speechSynthesis.speak = () => {}); });
  return { ctx, page };
}

// Records CDP screencast frames with their timestamps into dir; returns stop().
async function screencast(page, dir, maxWidth) {
  fs.mkdirSync(dir, { recursive: true });
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  cdp.on('Page.screencastFrame', async (f) => {
    const name = `f${String(frames.length).padStart(5, '0')}.jpg`;
    fs.writeFileSync(path.join(dir, name), Buffer.from(f.data, 'base64'));
    frames.push({ name, t: f.metadata.timestamp });
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth, maxHeight: 4000, everyNthFrame: 1 });
  return async () => {
    await cdp.send('Page.stopScreencast');
    await sleep(200);
    const lines = frames.map((f, i) => `file '${f.name}'\nduration ${((frames[i + 1]?.t ?? f.t + 0.04) - f.t).toFixed(4)}`);
    fs.writeFileSync(path.join(dir, 'list.txt'), lines.join('\n') + `\nfile '${frames.at(-1).name}'\n`);
    console.log(dir, frames.length, 'frames', (frames.at(-1).t - frames[0].t).toFixed(1), 's');
  };
}

const btn = (page, name, exact = false) => page.getByRole('button', { name, exact });
const shot = (page, name, full = false) => page.screenshot({ path: path.join(OUT, name + '.jpg'), type: 'jpeg', quality: 92, fullPage: full });

async function laptop(browser) {
  const { ctx, page } = await open(browser, { viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto(BASE + '/');
  await sleep(1500);
  let stop = await screencast(page, path.join(OUT, 'laptop-landing'), 1920);
  await sleep(26000);
  await stop();
  stop = await screencast(page, path.join(OUT, 'laptop-setup'), 1920);
  await btn(page, 'Run the demo').click();
  await sleep(1500);
  await btn(page, 'Continue', true).click();
  await sleep(9000);
  await btn(page, 'Bedroom', true).click().catch(() => {});
  await page.locator('.cap-shutter').first().click();
  await sleep(6000);
  await stop();
  await shot(page, 'laptop-room-checked');
  await ctx.close();
}

async function phone(browser) {
  const { ctx, page } = await open(browser, { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
  await page.goto(BASE + '/');
  await sleep(1200);
  await shot(page, 'p-landing');
  await btn(page, 'Run the demo').click();
  await page.locator('.permissions').waitFor();
  await shot(page, 'p-permissions');
  await btn(page, 'Continue', true).click();
  await page.locator('.cap-ring').waitFor();
  await sleep(2500);
  await shot(page, 'p-capture-room');
  await btn(page, 'Bedroom', true).click();
  await page.locator('.cap-shutter').first().click();
  await page.locator('.cap-took-status.is-done').waitFor({ timeout: 15000 });
  await sleep(600);
  await shot(page, 'p-room-checked');
  await btn(page, /^Next/).first().click();
  await sleep(500);
  await page.locator('.cap-skip').click();
  await sleep(800);
  await shot(page, 'p-gobag-step');
  await page.locator('.cap-shutter').first().click();
  await page.locator('.cap-took-status.is-done').waitFor({ timeout: 15000 });
  await sleep(600);
  await shot(page, 'p-gobag-checked');
  await btn(page, /^Next/).first().click();
  await sleep(500);
  await page.locator('.cap-skip').click();
  await page.locator('.review').waitFor();
  await sleep(1500);
  await shot(page, 'p-review', true);
  await btn(page, 'Save this place').click();
  await page.waitForFunction(() => document.querySelectorAll('.place-row').length === 2);
  await sleep(800);
  await shot(page, 'p-places');
  await page.locator('.place-row').nth(0).click();
  await page.waitForFunction(() => document.querySelector('.place .lm-route-line'));
  await sleep(1500);
  await shot(page, 'p-place', true);
  await btn(page, /My places/).first().click();
  await sleep(500);
  await btn(page, /Simulate an earthquake/).click();
  await sleep(1200);
  await shot(page, 'p-shaking');
  await sleep(2500);
  let stop = await screencast(page, path.join(OUT, 'p-after-walk'), 1170);
  await btn(page, 'Shaking has stopped').click();
  await sleep(2500);
  await page.locator('.em-speed').click().catch(() => {});
  await sleep(16000);
  await stop();
  await btn(page, 'Shelters that fit your household').waitFor({ timeout: 120000 });
  await sleep(1000);
  await shot(page, 'p-after-arrived', true);
  await btn(page, 'Shelters that fit your household').click();
  await sleep(1000);
  await shot(page, 'p-shelters', true);
  await btn(page, 'Leave emergency mode').click();
  await page.locator('.place-row', { hasText: 'Demo: Kamakura' }).click();
  await sleep(1500);
  await shot(page, 'p-kamakura', true);
  await page.goto(BASE + '/#about').catch(() => {});
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  await phone(browser);
  await laptop(browser);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
