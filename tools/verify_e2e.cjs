// Drives every SafeZone flow in a phone-sized Chromium against a running server.
// Usage: node tools/verify_e2e.cjs <screenshot-dir> [base-url]
// Start the server with: SAFEZONE_FIXTURES=fixtures/demo MODEL_API_KEY=x python -m uvicorn safezone.app:create_app --factory --port 8000
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = process.argv[2];
const BASE = process.argv[3] ?? 'http://127.0.0.1:8000';
if (!OUT) { console.error('usage: node tools/verify_e2e.cjs <outdir> [base-url]'); process.exit(2); }
const ROOT = path.join(__dirname, '..');
const PHOTO = path.join(ROOT, 'demo', 'living_room.jpg');
const DEMO_COORDS = { longitude: -122.5099836, latitude: 37.7694736, accuracy: 15 };
const DEMO_ADDRESS = '1000 Great Highway, San Francisco, CA 94121';
const MOVE_WORDS = /\b(turn|walk|go now|route|meters|metres|inland|uphill|evacuate|leave|run|head (north|south|east|west|toward|back|inland|out))\b/i;
const EXPECTED_FAILS = /\/api\/(profile\?lat|scan)/;

const failures = [];
const expectedFails = [];
const check = (ok, msg) => { if (ok) console.log('ok  ', msg); else { failures.push(msg); console.log('FAIL', msg); } };
let shotN = 0;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function open(browser, name, opts = {}, { expectFailedApi = false } = {}) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: false,
    permissions: ['geolocation', 'camera'], geolocation: DEMO_COORDS, ...opts,
  });
  await ctx.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  const page = await ctx.newPage();
  const voice = [];
  page.on('console', (m) => {
    const t = m.text();
    if (t.startsWith('[voice')) voice.push({ at: Date.now(), text: t.replace(/^\[voice[^\]]*\] /, '') });
    const where = m.location()?.url ?? '';
    if (expectFailedApi && /Failed to load resource/.test(t) && EXPECTED_FAILS.test(where)) { expectedFails.push(where); return; }
    if (m.type() === 'error' && !/fonts\.(googleapis|gstatic)|ERR_INTERNET_DISCONNECTED/.test(t + where)) {
      failures.push(`${name} console error: ${t}`);
      console.log('FAIL', `${name} console error: ${t}`);
    }
  });
  page.on('pageerror', (e) => { failures.push(`${name} page error: ${e.message}`); console.log('FAIL', `${name} page error: ${e.message}`); });
  const shot = async (label, full = false) => {
    shotN += 1;
    await page.screenshot({ path: path.join(OUT, `${String(shotN).padStart(2, '0')}-${name}-${label}.png`), fullPage: full });
  };
  return { ctx, page, voice, shot };
}

const btn = (page, name, exact = false) => page.getByRole('button', { name, exact });
const text = (page, sel = 'body') => page.locator(sel).first().innerText();
const waitFor = (page, fn, arg, timeout = 15000) => page.waitForFunction(fn, arg, { timeout }).then(() => true, () => false);
const visible = (loc, timeout = 15000) => loc.first().waitFor({ state: 'visible', timeout }).then(() => true, () => false);

async function landing(browser) {
  const { ctx, page, shot } = await open(browser, 'landing');
  await page.goto(BASE + '/');
  check(await visible(page.locator('.landing svg.nb')), 'landing draws the neighborhood svg');
  check(await page.locator('svg.nb.nb-animate').count() === 1, 'landing animates by default');
  for (const name of ['Map my home', 'Run the demo']) check(await btn(page, name).isVisible(), `landing shows "${name}"`);
  check(await btn(page, /My places/).count() === 0, 'landing hides My places with nothing saved');
  await shot('default');
  await ctx.close();

  const r = await open(browser, 'landing-reduced', { reducedMotion: 'reduce' });
  await r.page.goto(BASE + '/');
  await visible(r.page.locator('svg.nb'));
  check(await r.page.locator('svg.nb.nb-animate').count() === 0, 'reduced motion: neighborhood is the static frame');
  const anims = await r.page.evaluate(() => document.getAnimations().length);
  check(anims === 0, `reduced motion: no running animations (${anims})`);
  await r.shot('reduced-motion');
  await r.ctx.close();
}

async function demoFlow(browser) {
  const demo = await (await fetch(`${BASE}/api/demo`)).json();
  const jpGuidance = await (await fetch(`${BASE}/api/guidance?region=jp`)).json();
  const usGuidance = await (await fetch(`${BASE}/api/guidance`)).json();
  const room = demo.plan.rooms[0];
  const hazards = room.classified.filter((c) => c.role === 'hazard').length;
  const spot = room.spots[0].instruction;
  const { ctx, page, voice, shot } = await open(browser, 'demo');
  await page.goto(BASE + '/');
  await btn(page, 'Run the demo').click();

  check(await visible(page.locator('.permissions')), 'demo: permissions screen opens');
  check(await page.locator('.demo-banner').isVisible(), 'demo: permissions shows the DEMO banner');
  await shot('permissions');
  await btn(page, 'Continue', true).click();

  check(await visible(page.locator('.capture .cap-stage')), 'demo: capture opens');
  check(await visible(page.locator('.cap-ring')) && await page.locator('.cap-hint').isVisible(), 'demo: quality meter visible');
  check(await waitFor(page, () => !/Starting/.test(document.querySelector('.cap-hint-text')?.textContent ?? '')), 'demo: meter is measuring the demo photo');
  await shot('capture-room');
  await btn(page, 'Bedroom', true).click();
  await page.locator('.cap-shutter, button[aria-label*="photo" i]').first().click();
  check(await visible(page.locator('.cap-took')), 'demo: shutter saves the room and shows the took panel');
  check(await visible(page.locator('.cap-step.is-working, .cap-step.is-queued, .cap-step.is-done').first()), 'demo: step strip shows the room status');
  await shot('room-taken-working');
  check(await visible(page.locator('.cap-took-status.is-done'), 10000), 'demo: background scan finishes');
  await shot('room-checked');
  await btn(page, 'Add another room').click();
  check(await visible(page.locator('.cap-shutter')), '"Add another room" returns to the shutter on the room step');
  check((await page.locator('.cap-count').textContent()).includes('1 taken'), 'room step counts the room already taken');
  await page.locator('.cap-next').click();
  check(await visible(page.locator('.cap-step.is-current', { hasText: 'The way out' })), 'Next moves to "The way out"');
  await page.locator('.cap-back').click();
  check(await visible(page.locator('.cap-step.is-current', { hasText: 'Rooms' })), 'Back returns to the room step');
  await shot('after-back');
  await page.locator('.cap-next').click();
  for (const title of ['The way out', 'Go bag', 'Gas shutoff']) {
    check(await visible(page.locator('.cap-step.is-current', { hasText: title })), `capture reaches "${title}"`);
    await page.locator('.cap-skip').click();
  }
  check(await visible(page.locator('.review')), 'skipping the last step goes to review');
  await btn(page, /Back to photos/).click();
  check(await visible(page.locator('.capture')), 'review Back returns to capture');
  check(await page.locator('.cap-step.is-skipped', { hasText: 'Go bag' }).count() === 1, 'go bag shows as skipped');
  await page.locator('.cap-step', { hasText: 'Go bag' }).click();
  await page.locator('.cap-shutter').click();
  check(await visible(page.locator('.cap-took')), 'go bag photo taken over the skip');
  check(await page.locator('.cap-step.is-skipped', { hasText: 'Go bag' }).count() === 0, 'taking the go bag photo undoes its skip');
  check(await visible(page.locator('.cap-took-status.is-done'), 10000), 'go bag check finishes');
  await shot('gobag-checked');
  await btn(page, /Next: Gas shutoff/).click();
  await page.locator('.cap-skip').click();

  check(await visible(page.locator('.review')), 'demo: review opens');
  check(await visible(page.locator('.review .flag')), 'review shows building flags');
  check(await page.locator('.review .flag.tone-alert').count() >= 1, 'review flags the tsunami hazard area');
  const chip = page.locator('.review .chip', { hasText: 'Medical needs' });
  const before = await chip.getAttribute('aria-pressed');
  await chip.click();
  await waitFor(page, (b) => document.querySelector('.review .chips .chip:nth-child(3)')?.getAttribute('aria-pressed') !== b, before, 3000);
  check(await chip.getAttribute('aria-pressed') !== before, 'household chip toggles');
  await chip.click();
  await waitFor(page, (b) => document.querySelector('.review .chips .chip:nth-child(3)')?.getAttribute('aria-pressed') === b, before, 3000);
  check(await chip.getAttribute('aria-pressed') === before, 'household chip toggles back');
  check(await visible(page.locator('.review .room .overlay')), 'review shows the room result');
  check(await page.locator('.review .room .ov-balloon').count() === hazards, `review room marks ${hazards} hazards`);
  check((await page.locator('.review .room .room-name').textContent()).trim() === 'Bedroom', 'review room keeps the chosen name');
  const gobag = page.locator('.review section', { has: page.locator('h2', { hasText: 'Go bag' }) });
  if (demo.gobag) {
    check(await gobag.count() === 1, 'review shows the go bag card');
    check(await gobag.locator('.tag-sample').count() === (demo.gobag.provenance === 'sample' ? 1 : 0), 'go bag card is labelled sample when it is sample');
  }
  const kindChip = (k) => page.locator('.review .chip', { hasText: new RegExp(`^${k}$`) });
  await kindChip('Work').click();
  check(await visible(page.locator('.review .chip[aria-pressed=true]', { hasText: /^Work$/ }), 3000), 'name chip Work selects');
  await kindChip('Home').click();
  check(await visible(page.locator('.review .chip[aria-pressed=true]', { hasText: /^Home$/ }), 3000), 'name chip Home selects');
  check(await page.locator('.review input[aria-label="Place name"]').inputValue() === 'Demo: Ocean Beach', 'kind chips keep the typed place name');
  await shot('review', true);
  await btn(page, 'Save this place').click();

  check(await visible(page.locator('.places .place-row')), 'save opens places');
  await waitFor(page, () => document.querySelectorAll('.place-row').length === 2, null, 5000);
  const rows = page.locator('.place-row');
  check(await rows.count() === 2, 'places lists two demo places');
  check((await rows.nth(0).innerText()).includes('Demo: Ocean Beach'), 'Demo: Ocean Beach is first');
  check((await rows.nth(1).innerText()).includes('Demo: Kamakura'), 'Demo: Kamakura is second');
  for (let i = 0; i < 2; i++) {
    check(await rows.nth(i).locator('.place-flag').count() === 1 && await rows.nth(i).locator('.place-seal').count() === 1, `place ${i + 1} has a hazard flag and a seal`);
  }
  check(await page.locator('.places .standby').isVisible(), 'places shows standby');
  await shot('places');

  await rows.nth(0).click();
  check(await visible(page.locator('.place .room .overlay')), 'place shows the room overlay');
  check(await page.locator('.place .routemap').count() === 1, 'place shows the route map');
  check(await page.locator('.place .shelter').count() === demo.plan.shelters.matches.length, 'place lists the shelters');
  await shot('place', true);
  await btn(page, /My places/).first().click();
  check(await visible(page.locator('.places')), 'place Back returns to places');

  voice.length = 0;
  const simAt = Date.now();
  await btn(page, /Simulate an earthquake/).click();
  check(await visible(page.locator('.em-shaking')), 'simulate opens shaking');
  const shakeAt = Date.now();
  await shot('shaking');
  const hidden = await page.evaluate(() => {
    const dockTop = document.querySelector('.em-dock').getBoundingClientRect().top;
    return [...document.querySelectorAll('.em-spot, .em-steps li, .em-special')].filter((el) => el.getBoundingClientRect().bottom > dockTop).map((el) => el.textContent.slice(0, 30));
  });
  check(hidden.length === 0, `nothing on the shaking screen sits behind the bar at 390x844 (${JSON.stringify(hidden)})`);
  await page.locator('.em-dch').click();
  await sleep(300);
  check(await page.locator('.em-shaking').count() === 1, 'a tap in the first 3 s does not leave shaking');
  await btn(page, 'Shaking has stopped').click();
  await sleep(200);
  check(await page.locator('.em-shaking').count() === 1, '"Shaking has stopped" in the first 3 s does not leave shaking');
  const lines = voice.map((v) => v.text);
  check(lines[0] === 'This is a demo.', `shaking says "This is a demo." first (${JSON.stringify(lines[0])})`);
  check(lines[1] === `Drop, cover and hold on. ${spot}`, 'shaking says Drop, cover and hold on with the saved spot');
  await sleep(Math.max(0, 3200 - (Date.now() - shakeAt)));
  const shakingLines = voice.filter((v) => v.at >= simAt).map((v) => v.text);
  const moving = shakingLines.filter((t) => MOVE_WORDS.test(t));
  check(moving.length === 0, `no route or movement words spoken during shaking (${JSON.stringify(moving)})`);
  const leaveAt = Date.now();
  await page.locator('.em-dch').click();
  check(await visible(page.locator('.em-after')), 'after 3 s a tap leaves shaking for after');
  check(await page.locator('.em-after .routemap').count() === 1, 'after shows the route map');
  await btn(page, /Walker speed/).click();
  await shot('after');
  const goNow = usGuidance.go_now;
  const arrived = await (async () => {
    const until = Date.now() + 120000;
    while (Date.now() < until) {
      if (voice.some((v) => v.at >= leaveAt && /reached the end of the route|outside the mapped tsunami hazard area\. Stay there/.test(v.text))) return true;
      await sleep(500);
    }
    return false;
  })();
  await sleep(500);
  const afterLines = voice.filter((v) => v.at >= leaveAt).map((v) => v.text);
  check(afterLines.filter((t) => t.includes(goNow)).length === 1, 'go-now line spoken once');
  check(afterLines[0] === `This is a demo. ${goNow}`, 'after starts with the demo label and the go-now line');
  const steps = demo.plan.route.steps.map((s) => s.instruction.toLowerCase());
  const cued = afterLines.filter((t) => /^(Continue|In \d+ meters|Turn|Head|Arrive)/.test(t));
  // Instructions repeat ("Turn right" twice), so each cue takes the earliest matching step at or after the last one.
  let at = 0;
  const order = [];
  for (const t of cued) {
    const i = steps.findIndex((s, k) => k >= at && t.toLowerCase().includes(s));
    order.push(i);
    if (i >= 0) at = i;
  }
  check(cued.length >= steps.length - 1, `demo walker produced turn cues (${cued.length} for ${steps.length} steps)`);
  check(order.every((i) => i >= 0), `turn cues come in route order (${order.join(',')})`);
  // Each turn's "now" cue is its instruction alone, so the sequence of those must be the route's turns in order.
  const nowCues = afterLines.filter((t) => steps.slice(1, -1).some((s) => t.toLowerCase() === `${s}.`)).map((t) => t.slice(0, -1).toLowerCase());
  check(JSON.stringify(nowCues) === JSON.stringify(steps.slice(1, -1)), `every turn is announced at the turn, in order (${nowCues.join(' / ')})`);
  console.log('     after voice:', JSON.stringify(afterLines));
  check(afterLines[1] === `${demo.plan.route.steps[0].instruction}.`, `first route step spoken right after go-now (${JSON.stringify(afterLines[1])})`);
  check(arrived, 'arrival line spoken');
  check(afterLines.includes(usGuidance.stay_away), 'stay-away line spoken on arrival');
  await shot('after-arrived', true);
  await btn(page, 'Shelters that fit your household').click();
  check(await visible(page.locator('.em-shelters .shelter')), 'shelters screen lists shelters');
  const shelterOrder = await page.locator('.em-shelters .shelter h4').allInnerTexts();
  check(JSON.stringify(shelterOrder) === JSON.stringify(demo.plan.shelters.matches.map((m) => m.shelter.name)), `shelters in the plan's order (${shelterOrder.join(', ')})`);
  const shelterWalk = demo.plan.shelters.matches.map((m) => m.walk_min);
  const roomFirst = demo.plan.shelters.matches.map((m) => (m.fill_ratio != null && m.fill_ratio < 0.8 ? 0 : 1));
  check(roomFirst.every((g, i) => i === 0 || g > roomFirst[i - 1] || (g === roomFirst[i - 1] && shelterWalk[i] >= shelterWalk[i - 1])), 'shelters that report room first, then by walking time');
  check((await text(page, '.em-shelters')).includes('rank first'), 'a demoted shelter card says why it ranks lower');
  await shot('shelters', true);
  await btn(page, 'Leave emergency mode').click();
  check(await visible(page.locator('.places')), 'leaving the emergency returns to places');

  await page.locator('.place-row', { hasText: 'Demo: Kamakura' }).click();
  check(await visible(page.locator('.place')), 'Kamakura place opens');
  check(await visible(page.locator('.place .route-site')), 'Kamakura place shows the designated evacuation site');
  await shot('kamakura-place', true);
  await btn(page, /My places/).first().click();
  voice.length = 0;
  await btn(page, /Simulate an earthquake/).click();
  await visible(page.locator('.em-shaking'));
  check((await text(page, '.em-shaking')).includes(jpGuidance.during[0]), 'Kamakura shaking uses Japan guidance');
  check(!(await text(page, '.em-shaking')).includes('No saved place'), 'Kamakura shaking does not claim no place is saved');
  await shot('kamakura-shaking');
  await sleep(3200);
  await btn(page, 'Shaking has stopped').click();
  check(await visible(page.locator('.em-after')), 'Kamakura after opens');
  const jpText = await text(page, '.em-after');
  check(jpText.includes(jpGuidance.after[0]), 'Kamakura after uses Japan after-steps');
  check(jpText.includes(jpGuidance.go_now), 'Kamakura after shows the Japan go-now line');
  check(jpText.includes('Sample site A (hill)') && /designated evacuation site/i.test(jpText), 'Kamakura after shows the designated evacuation site');
  check(voice.some((v) => v.text.includes(jpGuidance.go_now)), 'Kamakura after speaks the Japan go-now line');
  const jpDemo = await (await fetch(`${BASE}/api/demo?region=jp`)).json();
  const jpFirst = `${jpDemo.plan.route.steps[0].instruction}.`;
  check(await waitFor(page, (t) => performance.now() > 0 && [...document.querySelectorAll('.em-next')].some((el) => el.textContent.length > 0), null, 5000)
    && voice.some((v) => v.text === jpFirst), `Kamakura after speaks the first turn of the site route (${JSON.stringify(jpFirst)})`);
  check(!voice.some((v) => /outside the mapped tsunami hazard area/.test(v.text)), 'Kamakura never claims to be outside a hazard area it has no polygons for');
  await shot('kamakura-after', true);
  await btn(page, 'Leave emergency mode').click();
  await visible(page.locator('.places'));

  await btn(page, 'Exit demo').click();
  check(await visible(page.locator('.landing')), 'Exit demo with only demo places returns to landing');
  const left = await page.evaluate(() => new Promise((res) => {
    const r = indexedDB.open('safezone');
    r.onsuccess = () => { const g = r.result.transaction('kv').objectStore('kv').get('places'); g.onsuccess = () => res(g.result ?? []); };
  }));
  check(left.filter((p) => p.demo).length === 0, 'Exit demo removes the demo places from IndexedDB');
  await shot('exit-demo');
  await ctx.close();
}

async function realFlow(browser) {
  const { ctx, page, voice, shot } = await open(browser, 'real', {}, { expectFailedApi: true });
  const profileCalls = [];
  page.on('request', (r) => { if (r.url().includes('/api/profile')) profileCalls.push(r.url()); });
  await page.goto(BASE + '/');
  await btn(page, 'Map my home').click();
  check(await visible(page.locator('.permissions')), 'real: permissions opens');
  check(await page.locator('.demo-banner').count() === 0, 'real: no DEMO banner');
  await btn(page, 'Allow camera and location').click();
  check(await visible(page.locator('.capture .cap-stage'), 10000), 'real: camera granted opens capture');
  check(await waitFor(page, () => document.querySelector('.cap-video')?.videoWidth > 0, null, 10000), 'real: live camera preview plays');
  await waitFor(page, () => /Location not found|Checking/.test(document.querySelector('.cap-loc')?.textContent ?? '') === false || /not found/.test(document.querySelector('.cap-loc')?.textContent), null, 10000);
  check(profileCalls.some((u) => /lat=37\.76947/.test(u) && /lon=-122\.50998/.test(u)), 'real: profile asked by GPS (/api/profile?lat&lon)');
  check(await waitFor(page, () => /not found|type the address/i.test(document.querySelector('.cap-loc')?.textContent ?? ''), null, 15000), 'real: GPS lookup without a fixture falls back to typing the address');
  await shot('capture-camera');
  await page.locator('.cap-shutter, button[aria-label*="photo" i]').first().click();
  check(await visible(page.locator('.cap-took')), 'real: shutter captures the camera frame');
  check(await visible(page.locator('.cap-took-status.is-failed'), 30000), 'real: scan of an unrecorded frame fails cleanly');
  check(await btn(page, 'Try again').isVisible(), 'real: failed shot offers Try again');
  await shot('scan-failed');
  await btn(page, 'Try again').click();
  check(await visible(page.locator('.cap-took-status.is-failed'), 30000), 'real: Try again fails cleanly again');
  await btn(page, /^Next/).first().click().catch(() => {});
  if (!(await page.locator('.cap-step.is-current', { hasText: 'Rooms' }).count())) await page.locator('.cap-step', { hasText: 'Rooms' }).click();
  const chooser = page.waitForEvent('filechooser');
  await page.locator('.cap-library').click();
  await (await chooser).setFiles(PHOTO);
  check(await visible(page.locator('.cap-took-status.is-done'), 30000), 'real: library photo of the recorded room is checked');
  await btn(page, /^Next/).first().click();
  for (let i = 0; i < 3; i++) await page.locator('.cap-skip').click();

  check(await visible(page.locator('.review')), 'real: review opens');
  const failedCard = page.locator('.review .shot-pending');
  check(await failedCard.count() === 1 && await failedCard.locator('button', { hasText: 'Try again' }).count() === 1
    && await failedCard.locator('button', { hasText: 'Remove' }).count() === 1, 'real: review shows the failed shot with Try again and Remove');
  check(await page.locator('.review .address-form').isVisible(), 'real: review asks for the typed address');
  check(await btn(page, 'Save this place').isDisabled(), 'real: Save waits for an address');
  await shot('review-before-address', true);
  await failedCard.locator('button', { hasText: 'Remove' }).click();
  check(await waitFor(page, () => document.querySelectorAll('.review .shot-pending').length === 0, null, 3000), 'real: Remove drops the failed shot');
  await page.locator('.review input[name=address]').fill(DEMO_ADDRESS);
  await btn(page, 'Look up').click();
  check(await visible(page.locator('.review .flag.tone-alert'), 20000), 'real: typed address loads the recorded building');
  check((await text(page, '.review-address')).includes('Great Highway'), 'real: review names the address');
  await page.locator('.review .chip', { hasText: /^Work$/ }).click();
  await page.locator('.review .chip', { hasText: /^School$/ }).click();
  check(await waitFor(page, () => document.querySelector('.review input[aria-label="Place name"]')?.value === 'School', null, 3000), 'real: an untyped name follows the kind chip');
  await page.locator('.review .chip', { hasText: /^Home$/ }).click();
  await waitFor(page, () => document.querySelector('.review input[aria-label="Place name"]')?.value === 'Home', null, 3000);
  await page.locator('.review input[aria-label="Place name"]').fill('Beach house');
  await page.locator('.review input[aria-label="Place name"]').dispatchEvent('change');
  await shot('review-ready', true);
  await btn(page, 'Save this place').click();
  check(await visible(page.locator('.places .place-row'), 30000), 'real: Save opens places');
  check((await text(page, '.place-row')).includes('Beach house'), 'real: saved place keeps its name');
  check(await page.locator('.place-row .tag-demo').count() === 0, 'real: saved place is not labelled demo');
  await shot('places');

  check(await page.evaluate(async () => Boolean((await navigator.serviceWorker.ready).active)), 'service worker active');
  await waitFor(page, () => Boolean(navigator.serviceWorker.controller), null, 5000) || (await page.reload(), await visible(page.locator('.places')));
  await ctx.setOffline(true);
  await page.reload();
  check(await visible(page.locator('.places .place-row')), 'offline: reload opens places');
  await shot('offline-places');
  voice.length = 0;
  await btn(page, 'Emergency', true).click();
  check(await visible(page.locator('.em-shaking')), 'offline: emergency opens');
  const spotText = await text(page, '.em-shaking');
  check(/beach house/i.test(spotText), 'offline: shaking shows the saved place');
  check(await page.locator('.em-spot').count() === 1, 'offline: shaking shows the saved spot');
  check(voice.some((v) => v.text.startsWith('Drop, cover and hold on.') && v.text.length > 'Drop, cover and hold on.'.length), 'offline: voice reads the saved spot');
  check(!voice.some((v) => v.text === 'This is a demo.'), 'real: no demo label spoken');
  await shot('offline-shaking');
  await sleep(3200);
  await btn(page, 'Shaking has stopped').click();
  check(await visible(page.locator('.em-after .routemap')), 'offline: route view renders');
  check(await waitFor(page, () => document.querySelector('.rm-pos')?.getAttribute('visibility') === 'visible', null, 10000), 'offline: live GPS position shows on the map');
  await shot('offline-after', true);
  await btn(page, 'Leave emergency mode').click();
  check(await visible(page.locator('.places')), 'offline: leaving returns to places');
  check(expectedFails.some((u) => u.includes('/api/profile?lat')) && expectedFails.some((u) => u.includes('/api/scan')), 'real: the only failed requests were the unrecorded GPS lookup and scan');
  await ctx.setOffline(false);
  await ctx.close();
}

async function noPlaces(browser) {
  const { ctx, page, voice, shot } = await open(browser, 'empty');
  await page.goto(BASE + '/?screen=emergency');
  check(await visible(page.locator('.em-shaking')), 'empty: emergency link opens shaking');
  check((await text(page, '.em-shaking')).includes('No saved place on this device'), 'empty: shaking says no place is saved');
  await shot('shaking');
  await sleep(3200);
  await btn(page, 'Shaking has stopped').click();
  check(await visible(page.locator('.em-after')), 'empty: after opens');
  check((await text(page, '.em-after')).includes('No saved place on this device'), 'empty: after says no place is saved');
  check(await page.locator('.routemap, .turns, .em-turn').count() === 0, 'empty: no route drawn');
  await sleep(1500);
  check(!voice.some((v) => /^(Continue|In \d+ meters|Turn)/.test(v.text)), 'empty: no turn cues spoken');
  await shot('after', true);
  await btn(page, 'Leave emergency mode').click();
  check(await visible(page.locator('.landing')), 'empty: leaving goes to landing');
  await ctx.close();
}

async function migration(browser) {
  const plan = JSON.parse(fs.readFileSync(path.join(ROOT, 'demo', 'plan.json'), 'utf8')).plan;
  const { ctx, page, shot } = await open(browser, 'migrate');
  await page.goto(BASE + '/manifest.webmanifest');
  await page.evaluate((plan) => new Promise((res, rej) => {
    const r = indexedDB.open('safezone', 1);
    r.onupgradeneeded = () => { r.result.createObjectStore('kv'); r.result.createObjectStore('images'); };
    r.onsuccess = () => {
      const tx = r.result.transaction('kv', 'readwrite');
      tx.objectStore('kv').put({ plan }, 'saved');
      tx.oncomplete = () => { r.result.close(); res(); };
      tx.onerror = () => rej(tx.error);
    };
  }), plan);
  await page.goto(BASE + '/');
  check(await visible(page.locator('.places .place-row')), 'migration: app opens to places');
  check(await page.locator('.place-row').count() === 1, 'migration: old plan shows as one place');
  check(await page.locator('.place-row .tag-demo').count() === 0, 'migration: migrated plan is not labelled demo');
  await shot('places');
  await page.reload();
  check(await visible(page.locator('.places .place-row')) && await page.locator('.place-row').count() === 1, 'migration: survives a reload without duplicating');
  await page.locator('.place-row').click();
  check(await visible(page.locator('.place .routemap')), 'migration: migrated place opens with its route');
  await ctx.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const only = process.env.ONLY?.split(',');
  const suites = { landing, demoFlow, realFlow, noPlaces, migration };
  for (const [name, run] of Object.entries(suites)) {
    if (only && !only.includes(name)) continue;
    console.log(`\n== ${name}`);
    try { await run(browser); } catch (e) { failures.push(`${name} crashed: ${e.message.split('\n')[0]}`); console.log('FAIL', `${name} crashed:`, e.message); }
  }
  await browser.close();
  console.log(failures.length ? `\n${failures.length} FAILED:\n${failures.join('\n')}` : '\nALL CHECKS PASSED');
  process.exit(failures.length ? 1 : 0);
})();
