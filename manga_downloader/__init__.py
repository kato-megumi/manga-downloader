"""Manga downloader package."""

from .sources.base import BaseClient, Chapter, Manga
from .sources.kisslove import KissLoveClient
from .sources.mangakatana import MangaKatanaClient
from .sources.registry import get_client, list_sources

__all__ = [
	"BaseClient",
	"Chapter",
	"Manga",
	"KissLoveClient",
	"MangaKatanaClient",
	"get_client",
	"list_sources",
]
