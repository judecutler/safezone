"""Standalone probe: calls each outside API once and saves the raw responses.

No dependencies beyond the Python 3 standard library and no SafeZone code.
Usage (the key comes from the environment or a .env file next to this script or in the current folder):
    python probe_apis.py path/to/room.jpg
    PowerShell: $env:META_API_KEY = "your-key"; python probe_apis.py path\to\room.jpg
It writes probe_out.json next to itself. The key is never written to the file.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "SafeZone/0.1 (Meta hackathon earthquake and tsunami prep)"


def _dotenv():
    for folder in (Path(__file__).resolve().parent, Path.cwd()):
        env = folder / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                if sep and not key.strip().startswith("#"):
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_dotenv()
BASE = os.environ.get("META_API_BASE", "https://api.meta.ai/v1").rstrip("/")
KEY = os.environ.get("META_API_KEY", "")
HOME = (-122.51005, 37.76966)
OUT = Path(__file__).with_name("probe_out.json")


def call(method, url, params=None, body=None, headers=None, timeout=120):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": UA, **(headers or {})}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, text = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - a probe records every failure
        status, text = 0, repr(e)
    return {"url": url.split("?")[0], "status": status, "seconds": round(time.time() - started, 2), "text": text[:200_000]}


def main():
    photo = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    auth = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    results = {"key_loaded": bool(KEY), "photo": str(photo) if photo else None}
    if not KEY:
        print("No META_API_KEY found (environment or .env); Meta calls will fail with 401.")
    if not photo:
        print("No photo path given; SAM 3.1 and Muse Spark calls are skipped.")
    results["meta_models"] = call("GET", f"{BASE}/models", headers=auth)
    if photo and KEY:
        image_url = "data:image/jpeg;base64," + base64.b64encode(photo.read_bytes()).decode()
        results["sam_wardrobe"] = call("POST", f"{BASE}/responses", headers={**auth, "Accept": "text/event-stream"}, body={
            "model": "sam-3.1", "stream": True, "metadata": {"include_confidence": "true"},
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": "wardrobe"}, {"type": "input_image", "image_url": image_url}]}]})
        for model in ("muse-spark-1.3", "muse-spark-1.1"):
            results[f"muse_{model}"] = call("POST", f"{BASE}/chat/completions", headers=auth, body={
                "model": model, "reasoning_effort": "low",
                "response_format": {"type": "json_schema", "json_schema": {"name": "probe", "strict": True, "schema": {
                    "type": "object", "additionalProperties": False, "required": ["tallest_object", "table_visible"],
                    "properties": {"tallest_object": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                   "table_visible": {"type": "boolean"}}}}},
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "Name the tallest piece of furniture and say whether a table is visible."},
                    {"type": "image_url", "image_url": {"url": image_url}}]}]})
    cgs = "https://gis.conservation.ca.gov/server/rest/services/CGS/IW_Tsunami_Hazard_Area/FeatureServer/0/query"
    results["cgs_point"] = call("GET", cgs, {
        "geometry": f"{HOME[0]},{HOME[1]}", "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "Evacuate,County,Map_Link",
        "returnGeometry": "false", "f": "json"})
    results["datasf_softstory"] = call("GET", "https://data.sfgov.org/resource/beah-shgi.json", {"$limit": 3})
    results["osrm_foot"] = call("GET", "https://routing.openstreetmap.de/routed-foot/route/v1/foot/"
                                f"{HOME[0]},{HOME[1]};-122.5060,37.7716", {"overview": "false", "steps": "true"})
    results["fema_open_shelters"] = call("GET", "https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query",
                                         {"where": "1=1", "outFields": "*", "resultRecordCount": 3, "f": "json"})
    OUT.write_text(json.dumps(results, indent=1))
    for name, r in results.items():
        if isinstance(r, dict):
            print(f"{name:28s} {r['status']}  {r['seconds']}s  {'' if r['status'] == 200 else r['text'][:120]}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
