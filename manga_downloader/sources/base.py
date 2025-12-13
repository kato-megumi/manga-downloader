from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64) Gecko/20100101 Firefox/121.0"


@dataclass
class Manga:
    slug: str
    title: str
    cover: Optional[str]


@dataclass
class Chapter:
    id: str
    slug: str
    number: Optional[str]
    title: str


class BaseClient:
    name: str

    def __init__(self, base_url: str, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Referer": self.base_url,
            }
        )

    def search(self, query: str, page: int = 1) -> List[Manga]:
        raise NotImplementedError

    def manga_details(self, slug: str) -> Dict[str, Any]:
        raise NotImplementedError

    def chapters(self, slug: str) -> List[Chapter]:
        raise NotImplementedError

    def chapter_pages(self, chapter_id: str) -> List[str]:
        raise NotImplementedError
