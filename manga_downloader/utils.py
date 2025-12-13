from __future__ import annotations

import os
import re
from pathlib import Path


_INVALID_WIN_CHARS = r'<>:"/\\|?*'
_INVALID_WIN_RE = re.compile(f"[{re.escape(_INVALID_WIN_CHARS)}]")


def sanitize_filename(name: str, replacement: str = "_") -> str:
    cleaned = _INVALID_WIN_RE.sub(replacement, name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "untitled"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def guess_ext_from_url(url: str) -> str:
    base = url.split("?")[0]
    _, ext = os.path.splitext(base)
    if not ext:
        return ".jpg"
    return ext
