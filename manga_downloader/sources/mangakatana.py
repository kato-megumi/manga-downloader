from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseClient, Chapter, Manga

BASE_URL = "https://mangakatana.com"


class MangaKatanaClient(BaseClient):
    name = "mangakatana"

    _image_array_name_regex = re.compile(r"data-src['\"],\s*(\w+)")
    _image_url_regex = re.compile(r"'([^']*)'")

    def __init__(self, base_url: str = BASE_URL, timeout: int = 20) -> None:
        super().__init__(base_url=base_url, timeout=timeout)

    def search(self, query: str, page: int = 1) -> List[Manga]:
        if query:
            params = {"search": query, "search_by": "book_name"}
            url = f"{self.base_url}/page/{page}"
            resp = self.session.get(url, params=params, timeout=self.timeout)
        else:
            url = f"{self.base_url}/manga/page/{page}"
            resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_manga_list(soup)

    def manga_details(self, slug: str) -> Dict[str, Any]:
        url = self._abs_url(slug)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.select_one("h1.heading")
        name = title.get_text(strip=True) if title else slug
        return {"name": name, "title": name, "slug": slug}

    def chapters(self, slug: str) -> List[Chapter]:
        url = self._abs_url(slug)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        chapters: List[Chapter] = []
        for row in soup.select("tr:has(.chapter)"):
            anchor = row.select_one("a")
            if not anchor or not anchor.get("href"):
                continue
            href = anchor["href"].strip()
            title = anchor.get_text(strip=True)
            number = self._extract_chapter_number(title)
            chapters.append(
                Chapter(
                    id=self._normalize_slug(href),
                    slug=self._normalize_slug(href),
                    number=number,
                    title=title,
                )
            )
        return chapters

    def chapter_pages(self, chapter_id: str) -> List[str]:
        url = self._abs_url(chapter_id)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        script_text = None
        for script in soup.find_all("script"):
            data = script.string or script.get_text()
            if data and "data-src" in data:
                script_text = data
                break
        if not script_text:
            return []
        name_match = self._image_array_name_regex.search(script_text)
        if not name_match:
            return []
        array_name = name_match.group(1)
        array_regex = re.compile(rf"var\s+{re.escape(array_name)}\s*=\s*\[([^\]]*)\]")
        array_match = array_regex.search(script_text)
        if not array_match:
            return []
        url_blob = array_match.group(1)
        return [m.group(1) for m in self._image_url_regex.finditer(url_blob)]

    def _parse_manga_list(self, soup: BeautifulSoup) -> List[Manga]:
        mangas: List[Manga] = []
        for item in soup.select("div#book_list > div.item"):
            anchor = item.select_one("div.text > h3 > a")
            if not anchor or not anchor.get("href"):
                continue
            title = anchor.get_text(strip=True)
            slug = self._normalize_slug(anchor["href"])
            img = item.select_one("img")
            cover = None
            if img and img.get("src"):
                cover = urljoin(self.base_url + "/", img["src"])
            mangas.append(Manga(slug=slug, title=title, cover=cover))
        return mangas

    def _normalize_slug(self, href: str) -> str:
        parsed = urlparse(href)
        if parsed.scheme and parsed.netloc:
            return parsed.path
        return href if href.startswith("/") else f"/{href}"

    def _abs_url(self, slug: str) -> str:
        return urljoin(self.base_url + "/", slug.lstrip("/"))

    def _extract_chapter_number(self, title: str) -> Optional[str]:
        match = re.search(r"(\d+\.\d+|\d+)", title)
        return match.group(1) if match else None
