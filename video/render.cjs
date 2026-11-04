// Renders the stage to one mp4 per scene. Usage: node video/render.cjs <stage dir> <out dir> [scene,...] [--stills t1,t2]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const [STAGE, OUT, only, stillsFlag, stills] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const tl = JSON.parse(fs.readFileSync(path.join(STAGE, 'timeline.json'), 'utf8'));

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto(process.env.STAGE_URL ?? 'http://127.0.0.1:8765/stage.html');
  await page.evaluate((t) => window.setup(t), tl);
  if (stillsFlag === '--stills') {
    for (const t of stills.split(',').map(Number)) {
      await page.evaluate((x) => window.seek(x), t);
      await page.screenshot({ path: path.join(OUT, `still-${t.toFixed(1)}.jpg`), type: 'jpeg', quality: 85 });
    }
    await browser.close(); return;
  }
  const want = only && only !== 'all' ? new Set(only.split(',')) : null;
  for (const [i, seg] of tl.segments.entries()) {
    if (want && !want.has(seg.scene)) continue;
    const name = `${String(i).padStart(2, '0')}-${seg.scene}`;
    const tmp = path.join(OUT, name + '.part.mp4');
    const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', '30', '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30', tmp], { stdio: ['pipe', 'inherit', 'inherit'] });
    const n = Math.round(seg.dur * 30);
    for (let f = 0; f < n; f++) {
      await page.evaluate((x) => window.seek(x), seg.start + f / 30);
      const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
      if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    }
    ff.stdin.end();
    const code = await new Promise((r) => ff.on('close', r));
    if (code !== 0) throw new Error(`${name}: ffmpeg ${code}`);
    fs.renameSync(tmp, path.join(OUT, name + '.mp4'));
    console.log(name, n, 'frames');
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
