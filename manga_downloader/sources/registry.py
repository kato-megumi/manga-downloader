from __future__ import annotations

from typing import List

from .base import BaseClient
from .kisslove import KissLoveClient
from .mangakatana import MangaKatanaClient


def list_sources() -> List[str]:
    return ["kisslove", "mangakatana"]


def get_client(source: str) -> BaseClient:
    source = source.lower().strip()
    if source == "mangakatana":
        return MangaKatanaClient()
    return KissLoveClient()
