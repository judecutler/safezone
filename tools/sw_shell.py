"""Rewrite SHELL in web/sw.js from the files on disk and bump VERSION, so the offline shell never misses a file.

    python tools/sw_shell.py
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
SKIP = {"sw.js"}


def shell_files() -> list[str]:
    files = [p for p in WEB.rglob("*") if p.is_file() and "tests" not in p.relative_to(WEB).parts
             and p.name not in SKIP and not p.name.endswith(".next")]
    return ["/", *sorted("/" + p.relative_to(WEB).as_posix() for p in files)]


def main() -> None:
    sw = WEB / "sw.js"
    text = sw.read_text()
    listing = "const SHELL = [\n" + "".join(f"  '{f}',\n" for f in shell_files()) + "];"
    text = re.sub(r"const SHELL = \[.*?\];", listing, text, count=1, flags=re.S)
    text = re.sub(r"const VERSION = 'safezone-v(\d+)';", lambda m: f"const VERSION = 'safezone-v{int(m[1]) + 1}';", text, count=1)
    sw.write_text(text)
    print(re.search(r"const VERSION = '([^']+)'", text)[1], len(shell_files()), "files")


if __name__ == "__main__":
    main()
