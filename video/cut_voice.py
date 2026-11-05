"""Cuts Jude's recordings into one cleaned wav per script block, shortening long pauses.

Usage: python video/cut_voice.py <out dir> <file.wav>:<id>=<start>-<end>[,...] ...
"""
import json, subprocess, sys, wave
from pathlib import Path
import numpy as np

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SR = 48000
durs = {}
for spec in sys.argv[2:]:
    path, blocks = spec.split(":", 1)
    with wave.open(path) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    for b in blocks.split(","):
        bid, rng = b.split("=")
        s, e = (float(x) for x in rng.split("-"))
        x = a[int(s * SR): int(e * SR)]
        n = SR // 20
        lv = np.array([np.sqrt((x[i:i + n] ** 2).mean()) for i in range(0, len(x) - n + 1, n)]) + 1e-9
        db = 20 * np.log10(lv)
        quiet = db < np.percentile(db, 15) + 9
        keep, run = np.ones(len(lv), bool), 0
        for i, q in enumerate(quiet):
            run = run + 1 if q else 0
            if run > 6:
                keep[i] = False
        first = np.argmax(~quiet); last = len(quiet) - np.argmax(~quiet[::-1])
        keep[:max(0, first - 2)] = False; keep[last + 3:] = False
        y = np.concatenate([x[i * n:(i + 1) * n] for i in range(len(lv)) if keep[i]])
        raw = OUT / f"{bid}.raw.wav"
        with wave.open(str(raw), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((y * 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                        "highpass=f=80,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,afade=t=in:d=0.03,areverse,afade=t=in:d=0.08,areverse",
                        "-ar", str(SR), "-ac", "1", str(OUT / f"{bid}.wav")], check=True)
        raw.unlink()
        durs[bid] = round(len(y) / SR, 2)
(OUT / "durations.json").write_text(json.dumps(durs, indent=1))
print(durs, round(sum(durs.values()), 1))
