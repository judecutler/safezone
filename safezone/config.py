import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
DEFAULT_BASE_URL = "https://api.meta.ai/v1"


def load_env(path: Path = ENV_PATH) -> None:
    """Read KEY=value lines from .env without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
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
            f"MODEL_API_KEY is not set. Looked for a file named exactly '.env' at {ENV_PATH} "
            f"(exists: {ENV_PATH.exists()}). It must contain a line MODEL_API_KEY=yourkey"
        )
    return key


def base_url() -> str:
    load_env()
    return os.environ.get("META_API_BASE", DEFAULT_BASE_URL).rstrip("/")
