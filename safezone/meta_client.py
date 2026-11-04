import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from . import config


class BudgetExceeded(RuntimeError):
    pass


class OfflineCacheMiss(RuntimeError):
    pass


class MetaClient:
    """POST to the Meta Model API, paying for each distinct request at most once.

    Identical requests are served from disk. Every network attempt is appended to a
    ledger that survives restarts, and attempts beyond max_calls are refused.
    """

    def __init__(self, cache_dir=None, max_calls=None, offline=None, transport=None):
        config.load_env()
        self.cache_dir = Path(cache_dir) if cache_dir else config.ROOT / ".cache" / "meta"
        self.ledger = self.cache_dir / "ledger.jsonl"
        self.max_calls = int(os.environ.get("MAX_API_CALLS", "15")) if max_calls is None else max_calls
        self.offline = os.environ.get("SAFEZONE_OFFLINE") == "1" if offline is None else offline
        self.transport = transport or self._http

    def calls_used(self) -> int:
        if not self.ledger.exists():
            return 0
        return sum(1 for line in self.ledger.read_text().splitlines() if line.strip())

    def post(self, path: str, payload: dict) -> dict:
        digest = hashlib.sha256(json.dumps([path, payload], sort_keys=True).encode()).hexdigest()
        cached = self.cache_dir / f"{digest}.json"
        if cached.exists():
            return json.loads(cached.read_text())
        if self.offline:
            raise OfflineCacheMiss(f"offline mode and no cached response for {path}")
        used = self.calls_used()
        if used >= self.max_calls:
            raise BudgetExceeded(
                f"{used} of {self.max_calls} allowed API calls already used. "
                "Raise MAX_API_CALLS in .env or delete the ledger to continue."
            )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a") as handle:
            handle.write(json.dumps({"path": path, "digest": digest}) + "\n")
        response = self.transport(path, payload)
        cached.write_text(json.dumps(response))
        return response

    def _http(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            config.base_url() + path,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {config.api_key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as reply:
                return json.loads(reply.read())
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP {error.code} from {path}: {error.read()[:400]!r}") from None
