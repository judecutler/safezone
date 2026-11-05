"""Lays the scenes on a timeline from the narration durations. Usage: python video/build_timeline.py <vo dir> <out.json> <lines.json>"""
import json, re, sys
from pathlib import Path

VO = Path(sys.argv[1])
DUR = json.loads((VO / "durations.json").read_text())
TEXT = {l["id"]: l["text"] for l in json.loads(Path(sys.argv[3]).read_text())}
# scene, narration, silence before the line, silence after, fixed length (no narration)
PLAN = [("tolls", "b01", 1.6, .3, None), ("dec5", "b02", .2, .3, None), ("title", "b04", .2, .3, None),
        ("gap", "b05", .2, .3, None), ("bench", "b06", .2, .4, None), ("hazard", "b07", .2, .3, None),
        ("sam", "b08a", .2, .1, None), ("muse", "b08b", .1, .3, None), ("guard", "b09", .2, .3, None),
        ("gobag", "b10", .2, .3, None), ("route", "b11", .2, .3, None), ("japan", "b12", .2, .3, None),
        ("reenact", "b13", .3, .3, None), ("react", None, 0, 0, 3.7), ("shake", "b14", .2, .3, None),
        ("clip", None, 0, 0, 8.0), ("after", "b15", .2, .4, None), ("close", "b16", .3, .4, None),
        ("end", "b17", .3, 2.0, None)]
SHOW = [("Safe Zone", "SafeZone"), ("Sam three point one", "SAM 3.1"), ("Meta A I", "Meta AI"), ("Ready dot gov", "Ready.gov"),
        ("thirty-one percent", "31%"), ("seventy percent", "70%"), ("twenty twenty-four", "2024"), ("twenty eleven", "2011"),
        ("December fifth", "December 5"), ("Five million", "5 million"), ("ten times", "10 times"), ("ten minutes", "10 minutes"),
        ("five minutes", "5 minutes")]


def show(s):
    for a, b in SHOW:
        s = s.replace(a, b)
    return s


segs, T = [], 0.0
for scene, vo, pre, post, fixed in PLAN:
    seg = {"scene": scene, "start": round(T, 3)}
    if vo:
        d = DUR[vo]
        text = TEXT[vo]
        caps, pos = [], 0
        for sent in re.findall(r".+?[.!?](?=\s|$)", text):
            a = pre + d * pos / len(text)
            pos += len(sent)
            caps.append({"at": round(a, 3), "end": round(pre + d * pos / len(text), 3), "text": show(sent.strip().lstrip(",; "))})
        seg.update(dur=round(pre + d + post, 3), vo={"id": vo, "at": pre, "dur": d, "text": text, "caps": caps})
    else:
        seg.update(dur=fixed, vo=None)
    if scene == "clip":
        seg["from"] = 0.8
    if scene == "after":
        seg["from"] = 9.3
    segs.append(seg)
    T += seg["dur"]
Path(sys.argv[2]).write_text(json.dumps({"fps": 30, "total": round(T, 3), "segments": segs}, ensure_ascii=False, indent=1))
print(f"total {T:.1f} s, {len(segs)} scenes")
