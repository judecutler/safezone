"""Kokoro TTS without espeak: words come from misaki's US dictionaries, unknown words from OVERRIDES.

Usage: python video/tts.py <models dir> <lines.json> <out dir> [voice]
lines.json: [{"id": "...", "text": "..."}]. Writes <id>.wav at 24 kHz and prints each duration.
"""
import json, re, sys, wave
from pathlib import Path
import numpy as np
import onnxruntime as ort

MODELS, LINES, OUT = map(Path, sys.argv[1:4])
VOICE = sys.argv[4] if len(sys.argv) > 4 else "af_heart"
SR = 24000
CFG = json.loads((MODELS / "kokoro-onnx/src/kokoro_onnx/config.json").read_text())
VOCAB = CFG["vocab"]
DATA = MODELS / "misaki/misaki/data"
DICT = {**json.loads((DATA / "us_silver.json").read_text()), **json.loads((DATA / "us_gold.json").read_text())}
OVERRIDES = json.loads((Path(__file__).parent / "pron.json").read_text())


def word_ps(w: str) -> str:
    for key in (w, w.lower(), w.capitalize()):
        if key in OVERRIDES:
            return OVERRIDES[key]
    for key in (w, w.lower(), w.capitalize()):
        v = DICT.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            v = v.get("DEFAULT") or next(x for x in v.values() if x)
        return v
    lw = w.lower()
    voiced = "aeiouəɪʊɔæɑɛʌɜrlmnŋbdgvðʒAIOWYᵊ"
    for suffix, base_of in (("'s", lambda x: x[:-2]), ("ies", lambda x: x[:-3] + "y"), ("s", lambda x: x[:-1])):
        if lw.endswith(suffix) and base_of(lw) in DICT:
            base = word_ps(base_of(lw))
            return base + ("ɪz" if base[-1] in "szʃʒ" else "z" if base[-1] in voiced else "s")
    for suffix, base_of in (("ed", lambda x: x[:-2]), ("ed", lambda x: x[:-1])):
        if lw.endswith(suffix) and base_of(lw) in DICT:
            base = word_ps(base_of(lw))
            return base + ("ɪd" if base[-1] in "td" else "d" if base[-1] in voiced else "t")
    for base_of in (lambda x: x[:-3], lambda x: x[:-3] + "e"):
        if lw.endswith("ing") and base_of(lw) in DICT:
            return word_ps(base_of(lw)) + "ɪŋ"
    raise KeyError(w)


def phonemize(text: str) -> str:
    out = []
    for tok in re.findall(r"[A-Za-z][A-Za-z'’\-]*|[.,!?;:—…]", text):
        if re.match(r"[.,!?;:—…]", tok):
            out.append({"—": ",", "…": "."}.get(tok, tok))
            continue
        parts = [p for p in re.split(r"-", tok.replace("’", "'")) if p]
        out.append(" ".join(word_ps(p) for p in parts))
    s = ""
    for t in out:
        s += t if t in ".,!?;:" else (" " + t if s else t)
    return s


def main():
    sess = ort.InferenceSession(str(MODELS / "kokoro-v1.0.onnx"))
    names = [i.name for i in sess.get_inputs()]
    tok_name = "input_ids" if "input_ids" in names else "tokens"
    dtype = {i.name: (np.int64 if "int64" in i.type else np.int32 if "int32" in i.type else np.float32) for i in sess.get_inputs()}
    voice = np.load(MODELS / "voices-v1.0.bin")[VOICE]
    OUT.mkdir(parents=True, exist_ok=True)
    missing = set()
    result = {}
    for line in json.loads(LINES.read_text()):
        try:
            ps = phonemize(line["text"])
        except KeyError as e:
            missing.add(str(e)); continue
        chunks = re.findall(r"[^.!?]+[.!?]?", ps)
        audio = []
        for c in chunks:
            ids = [VOCAB[ch] for ch in c.strip() if ch in VOCAB]
            if not ids:
                continue
            a = sess.run(None, {tok_name: np.array([[0, *ids, 0]], dtype=dtype[tok_name]),
                                "style": voice[min(len(ids), len(voice)) - 1].astype(np.float32),
                                "speed": np.array([line.get("speed", 1.0)], dtype=dtype["speed"])})[0].ravel()
            audio += [a, np.zeros(int(SR * 0.18), np.float32)]
        a = np.concatenate(audio[:-1])
        pcm = (np.clip(a, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(OUT / f"{line['id']}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
        result[line["id"]] = round(len(a) / SR, 2)
    if missing:
        print("MISSING", sorted(missing)); sys.exit(1)
    (OUT / "durations.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result))


main()
