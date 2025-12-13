from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from .base import BaseClient, Chapter, Manga

CLIENT_ID = "KL9K40zaSyC9K40vOMLLbEcepIFBhUKXwELqxlwTEF"
BASE_URL = "https://klz9.com"

FILTER_IMG = {
    "https://1.bp.blogspot.com/-ZMyVQcnjYyE/W2cRdXQb15I/AAAAAAACDnk/8X1Hm7wmhz4hLvpIzTNBHQnhuKu05Qb0gCHMYCw/s0/LHScan.png",
    "https://s4.imfaclub.com/images/20190814/Credit_LHScan_5d52edc2409e7.jpg",
    "https://s4.imfaclub.com/images/20200112/5e1ad960d67b2_5e1ad962338c7.jpg",
}

IMG_URL_MAPPING = {
    "imfaclub.com": "j1.jfimv2.xyz",
    "s2.imfaclub.com": "j2.jfimv2.xyz",
    "s4.imfaclub.com": "j4.jfimv2.xyz",
    "ihlv1.xyz": "j1.jfimv2.xyz",
    "s2.ihlv1.xyz": "j2.jfimv2.xyz",
    "s4.ihlv1.xyz": "j4.jfimv2.xyz",
    "h1.klimv1.xyz": "j1.jfimv2.xyz",
    "h2.klimv1.xyz": "j2.jfimv2.xyz",
    "h4.klimv1.xyz": "j4.jfimv2.xyz",
}


class KissLoveClient(BaseClient):
    name = "kisslove"

    def __init__(self, base_url: str = BASE_URL, timeout: int = 20) -> None:
        super().__init__(base_url=base_url, timeout=timeout)

    def _sig_headers(self) -> Dict[str, str]:
        ts = str(int(time.time()))
        payload = f"{ts}.{CLIENT_ID}"
        sig = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return {"X-Client-Sig": sig, "X-Client-Ts": ts}

    def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, headers=self._sig_headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, page: int = 1) -> List[Manga]:
        data = self._get_json(
            "api/manga/list",
            params={"search": query, "sort": "Popular", "order": "desc", "page": page},
        )
        items = data.get("items") if isinstance(data, dict) else data
        return [self._parse_manga(item) for item in items or []]

    def latest(self, page: int = 1, limit: int = 36) -> List[Manga]:
        data = self._get_json("api/manga", params={"page": page, "limit": limit})
        items = data.get("items") if isinstance(data, dict) else data
        return [self._parse_manga(item) for item in items or []]

    def trending(self) -> List[Manga]:
        data = self._get_json("api/manga/trending-daily")
        items = data if isinstance(data, list) else data.get("items", [])
        return [self._parse_manga(item) for item in items or []]

    def manga_details(self, slug: str) -> Dict[str, Any]:
        return self._get_json(f"api/manga/slug/{slug}")

    def chapters(self, slug: str) -> List[Chapter]:
        data = self.manga_details(slug)
        raw_chapters = data.get("chapters") if isinstance(data, dict) else []
        parsed = [self._parse_chapter(item) for item in raw_chapters or []]
        return sorted(parsed, key=self._chapter_sort_key, reverse=True)

    def chapter_pages(self, chapter_id: str) -> List[str]:
        data = self._get_json(f"api/chapter/{chapter_id}")
        content = data.get("content", "") if isinstance(data, dict) else ""
        urls = [line.strip() for line in content.splitlines() if line.strip()]
        urls = [u for u in urls if u not in FILTER_IMG]
        return [self._map_image_host(u) for u in urls]

    def _map_image_host(self, url: str) -> str:
        parsed = urlparse(url)
        new_host = IMG_URL_MAPPING.get(parsed.netloc)
        if not new_host:
            return url
        return urlunparse(parsed._replace(netloc=new_host))

    def _parse_manga(self, raw: Dict[str, Any]) -> Manga:
        slug = raw.get("slug") or raw.get("url") or raw.get("mangaSlug") or ""
        title = raw.get("name") or raw.get("title") or raw.get("mangaName") or slug
        cover = raw.get("cover") or raw.get("thumbnail") or raw.get("image")
        return Manga(slug=slug, title=title, cover=cover)

    def _parse_chapter(self, raw: Dict[str, Any]) -> Chapter:
        cid = raw.get("id") or raw.get("chapter_id") or raw.get("chapterId")
        slug = raw.get("slug") or raw.get("chapter_slug") or raw.get("chapterSlug")
        if cid is None:
            cid = slug or raw.get("chapter") or raw.get("title") or raw.get("name") or "unknown"
        if not slug:
            slug = str(cid)
        number = raw.get("chapter") or raw.get("chapterNumber") or raw.get("number")
        title = raw.get("title") or raw.get("name")
        if not title:
            title = f"Chapter {number}" if number else f"Chapter {slug}"
        return Chapter(id=str(cid), slug=str(slug), number=str(number) if number else None, title=title)

    def _chapter_sort_key(self, chapter: Chapter) -> float:
        if chapter.number is None:
            return -1.0
        try:
            return float(chapter.number)
        except ValueError:
            return -1.0
