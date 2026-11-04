// Renders web/og.png, the 1200x630 link preview, from the landing art. Run with the app served on :8000:
//   NODE_PATH=/opt/node22/lib/node_modules node tools/render_og.cjs
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  await ctx.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  const p = await ctx.newPage();
  await p.goto('http://127.0.0.1:8000/'); await p.waitForTimeout(1200);
  const art = await p.evaluate(() => document.querySelector('.landing-map').outerHTML);
  const css = await p.evaluate(async () => (await Promise.all([...document.querySelectorAll('link[rel=stylesheet]')].map((l) => fetch(l.href).then((r) => r.text())))).join('\n'));
  await p.setContent(`<html><head><style>${css}
    body{margin:0;width:1200px;height:630px;overflow:hidden;background:var(--paper)}
    .og-art{position:absolute;inset:0}
    .og-art .landing-map{height:630px!important;min-height:0}
    .og-art .landing-bar,.og-art .landing-top,.og-art .landing-mark,.og-art .landing-phase{display:none!important}
    .og-card{position:absolute;left:56px;top:50%;transform:translateY(-50%);width:600px;background:#fff;border:2px solid var(--ink);border-radius:24px;padding:36px 40px;box-shadow:0 12px 40px rgba(0,0,0,.18)}
    .og-card h1{font:800 54px/1.02 var(--f-cond);margin:0 0 16px;color:var(--ink)}
    .og-card p{font:400 24px/1.35 var(--f-body);margin:0;color:var(--ink)}
    .og-card .jp{font:500 20px/1 var(--f-jp);color:var(--muted);margin:0 0 18px;display:block}
    .og-brand{display:flex;gap:10px;align-items:center;font:800 22px/1 var(--f-cond);letter-spacing:.06em;margin-bottom:22px}
    .og-brand img{width:40px;height:40px;border-radius:9px}
    .og-card .og-meta{margin-top:18px;font:600 18px/1.3 var(--f-body);color:var(--muted)}
  </style></head><body><div class="og-art">${art}</div>
  <div class="og-card"><div class="og-brand"><img src="http://127.0.0.1:8000/icons/icon-192.png">SAFEZONE</div>
  <h1>Know your way to high ground.</h1><span class="jp">地震・津波への備え</span>
  <p>Prepare once for a coastal earthquake. When it comes, your phone talks you out.</p>
  <p class="og-meta">Built with Meta SAM 3.1 and Muse Spark</p></div></body></html>`);
  await p.waitForTimeout(800);
  await p.screenshot({ path: '/home/claude/safezone/web/og.png' });
  await b.close();
})();
