"""Builds the soundtrack: narration, synthesized siren, rumble, ticks and music bed, plus the two phone clips.

Usage: python video/mix.py <timeline.json> <vo dir> <react.wav> <phone.wav> <out.wav>
"""
import json, sys, wave
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly, butter, sosfilt

TL, VO, REACT, PHONE, OUT = sys.argv[1:6]
SR = 48000
tl = json.loads(Path(TL).read_text())
N = int((tl["total"] + .5) * SR)
mix = np.zeros((N, 2), np.float32)
voice_env = np.zeros(N, np.float32)
rng = np.random.default_rng(7)
seg = {s["scene"]: s for s in tl["segments"]}


def db(x): return 10 ** (x / 20)


def read_wav(path):
    with wave.open(str(path)) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    a = a.reshape(-1, ch)
    if ch == 1: a = np.repeat(a, 2, 1)
    if sr != SR: a = resample_poly(a, SR, sr, axis=0).astype(np.float32)
    return a


def put(a, t, gain=1.0):
    i = int(t * SR)
    a = a[: max(0, N - i)]
    mix[i:i + len(a)] += a * gain


def lp(x, hz, order=4): return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x, axis=0)
def hp(x, hz, order=2): return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x, axis=0)


def fade(a, fin=.02, fout=.05):
    n = len(a); e = np.ones(n, np.float32)
    k = int(fin * SR); e[:k] = np.linspace(0, 1, k) if k else e[:k]
    k = int(fout * SR); e[n - k:] = np.linspace(1, 0, k) if k else e[n - k:]
    return a * e[:, None]


# Narration -------------------------------------------------------------------------------------------------
for s in tl["segments"]:
    if s["vo"]:
        a = read_wav(Path(VO) / f"{s['vo']['id']}.wav")
        t = s["start"] + s["vo"]["at"]
        put(a, t, db(-1))
        i = int(t * SR); voice_env[i:i + len(a)] = 1

# Siren: a wail swept 650 to 1350 Hz, heard from a distance --------------------------------------------------
dur = seg["dec5"]["start"] + seg["dec5"]["dur"]
t = np.arange(int(dur * SR)) / SR
f = 1000 + 350 * np.sin(2 * np.pi * t / 4.2 - np.pi / 2)
ph = 2 * np.cumsum(f) * np.pi / SR
tone = np.tanh(2.2 * np.sin(ph)) * .6 + .25 * np.sin(2 * ph)
tone = lp(tone, 2600)
ir = rng.standard_normal(int(1.6 * SR)) * np.exp(-np.arange(int(1.6 * SR)) / (.45 * SR))
wet = np.convolve(tone, ir[:: 1])[: len(tone)] * .02
siren = (tone * .35 + wet)
env = np.clip(t / 1.2, 0, 1) * np.clip((dur - t) / 5, 0, 1)
siren = (siren * env).astype(np.float32)
pan = .5 + .25 * np.sin(2 * np.pi * t / 9)
put(np.stack([siren * (1 - pan), siren * pan], 1) * 2, 0, db(-24))

# Ticks as each death toll appears ---------------------------------------------------------------------------
tick = lp(rng.standard_normal(int(.25 * SR)), 900) * np.exp(-np.arange(int(.25 * SR)) / (.03 * SR))
low = np.sin(2 * np.pi * 52 * np.arange(int(.6 * SR)) / SR) * np.exp(-np.arange(int(.6 * SR)) / (.18 * SR))
for i in range(5):
    put(np.repeat((tick * .5)[:, None], 2, 1), .5 + i * 1.25, db(-10))
    put(np.repeat((low * .9)[:, None], 2, 1), .5 + i * 1.25, db(-8))

# Music bed: chords from summed sines with slow attack -------------------------------------------------------
def pad(freqs, length, gain, bright=1500):
    n = int(length * SR); tt = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * fq * tt + k) * (.6 if k % 2 else 1) for k, fq in enumerate(freqs))
    x += .3 * sum(np.sin(2 * np.pi * fq * 2.003 * tt) for fq in freqs)
    x = lp(x / len(freqs), bright)
    trem = 1 + .08 * np.sin(2 * np.pi * tt / 5.3)
    e = np.minimum(1, tt / 2.5) * np.minimum(1, (length - tt) / 2.5)
    return np.stack([x * trem * e, x * (2 - trem) * e], 1).astype(np.float32) * gain


def note(n): return 440 * 2 ** ((n - 69) / 12)


dark_end = seg["title"]["start"]
put(pad([note(33), note(40), note(45)], dark_end + 1.5, db(-20), 600), 0)
bright = [[57, 64, 69, 73], [54, 61, 66, 69], [50, 57, 62, 66], [52, 59, 64, 68]]
t0, t1 = seg["title"]["start"], seg["shake"]["start"]
step = (t1 - t0) / 8
for k in range(8):
    put(pad([note(n - 12) for n in bright[k % 4]], step + 2.5, db(-24), 2400), t0 + k * step - .5)
em0, em1 = seg["shake"]["start"], seg["close"]["start"]
put(pad([note(31), note(38), note(43)], em1 - em0 + 1.5, db(-20), 500), em0)
beat = np.sin(2 * np.pi * 48 * np.arange(int(.35 * SR)) / SR) * np.exp(-np.arange(int(.35 * SR)) / (.07 * SR))
for b in np.arange(em0 + 4.5, em1, .9):
    put(np.repeat((beat * .6)[:, None], 2, 1), b, db(-14))
put(pad([note(n - 12) for n in [57, 64, 69, 73, 76]], tl["total"] - em1 + .5, db(-22), 2600), em1 - .5)

# Rumble at the start of the shaking scene ------------------------------------------------------------------
n = int(4.5 * SR)
rum = lp(rng.standard_normal(n), 90, 4) * 6 * np.minimum(1, np.arange(n) / (.15 * SR)) * np.exp(-np.arange(n) / (1.8 * SR))
put(np.repeat(rum[:, None].astype(np.float32), 2, 1), em0, db(-3))

# Duck everything that isn't narration under the voice ------------------------------------------------------
k = int(.25 * SR)
env = np.convolve(voice_env, np.ones(k) / k, "same")
duck = (1 - .45 * np.clip(env, 0, 1)).astype(np.float32)
bed = mix.copy()
# narration is the only content where voice_env is 1 at full; ducking applies to the bed by rebuilding without VO
vo_only = np.zeros_like(mix)
for s in tl["segments"]:
    if s["vo"]:
        a = read_wav(Path(VO) / f"{s['vo']['id']}.wav") * db(-1)
        i = int((s["start"] + s["vo"]["at"]) * SR)
        vo_only[i:i + len(a)] += a[: N - i]
bed = (mix - vo_only) * duck[:, None]
mix = bed + vo_only

# The builder's reaction and the phone clip, with their own sound ------------------------------------------
r = read_wav(REACT)
put(fade(r[: int(seg["react"]["dur"] * SR)]), seg["react"]["start"], db(-2))
ph = read_wav(PHONE)
c = seg["clip"]
put(fade(ph[int(c["from"] * SR): int((c["from"] + c["dur"]) * SR)], .1, .2), c["start"], db(9))
a = seg["after"]
put(fade(ph[int(a["from"] * SR): int((a["from"] + 3.9) * SR)], .2, .2), a["start"], db(-6))
put(fade(ph[int(22 * SR): int((22 + a["dur"] - 3.9) * SR)], .2, .4), a["start"] + 3.9, db(-6))

peak = np.abs(mix).max()
mix = mix / peak * db(-1.5)
pcm = (mix * 32767).astype(np.int16)
with wave.open(OUT, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print(f"wrote {OUT}: {len(mix) / SR:.1f} s, peak was {20 * np.log10(peak):.1f} dB")
