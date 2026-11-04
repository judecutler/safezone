import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://api.meta.ai/v1"


def load_env(path: Path = ROOT / ".env") -> None:
    """Read KEY=value lines from .env without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def api_key() -> str:
    load_env()
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        raise RuntimeError(
            "MODEL_API_KEY is not set. Copy .env.example to .env and paste your key there."
        )
    return key


def base_url() -> str:
    load_env()
    return os.environ.get("META_API_BASE", DEFAULT_BASE_URL).rstrip("/")
