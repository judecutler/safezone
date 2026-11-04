"""Settings read once from the environment, with a `.env` file in the repo root as a fallback."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    meta_api_key: str | None
    meta_api_base: str
    vision_model: str
    segment_model: str


def load_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    return Settings(
        meta_api_key=os.environ.get("META_API_KEY") or None,
        meta_api_base=os.environ.get("META_API_BASE", "https://api.meta.ai/v1").rstrip("/"),
        vision_model=os.environ.get("META_VISION_MODEL", "muse-spark-1.3"),
        segment_model=os.environ.get("META_SEGMENT_MODEL", "sam-3.1"),
    )
