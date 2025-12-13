from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from rich.console import Console

from .sources.base import Chapter
from .sources.registry import get_client, list_sources
from .downloader import download_chapters_cli
from .tui import run_tui


console = Console()


def _print_manga_list(mangas) -> None:
    for idx, manga in enumerate(mangas, start=1):
        console.print(f"{idx:>3}. {manga.title} [{manga.slug}]", markup=False)


def _print_chapter_list(chapters: List[Chapter]) -> None:
    for idx, chapter in enumerate(chapters, start=1):
        num = f" ({chapter.number})" if chapter.number else ""
        console.print(f"{idx:>3}. {chapter.title}{num}", markup=False)


def _select_range(chapters: List[Chapter], start: int | None, end: int | None) -> List[Chapter]:
    if not chapters:
        return []
    s = start or 1
    e = end or len(chapters)
    s = max(1, min(s, len(chapters)))
    e = max(1, min(e, len(chapters)))
    if s > e:
        s, e = e, s
    return chapters[s - 1 : e]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manga-fetcher")
    parser.add_argument("--source", default="kisslove", choices=list_sources())
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("tui", help="Launch the TUI")

    search_p = sub.add_parser("search", help="Search manga")
    search_p.add_argument("query")
    search_p.add_argument("--page", type=int, default=1)

    info_p = sub.add_parser("info", help="Show manga details")
    info_p.add_argument("slug")

    download_p = sub.add_parser("download", help="Download chapters")
    download_p.add_argument("slug")
    download_p.add_argument("--start", type=int)
    download_p.add_argument("--end", type=int)
    download_p.add_argument("--output", type=Path, default=Path("downloads"))
    download_p.add_argument("--cbz", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        run_tui()
        return

    client = get_client(args.source)

    if args.command == "tui":
        run_tui()
        return

    if args.command == "search":
        mangas = client.search(args.query, page=args.page)
        _print_manga_list(mangas)
        return

    if args.command == "info":
        details = client.manga_details(args.slug)
        title = details.get("name") or details.get("title") or args.slug
        console.print(title)
        chapters = client.chapters(args.slug)
        _print_chapter_list(chapters)
        return

    if args.command == "download":
        details = client.manga_details(args.slug)
        title = details.get("name") or details.get("title") or args.slug
        chapters = client.chapters(args.slug)
        selected = _select_range(chapters, args.start, args.end)
        if not selected:
            console.print("No chapters found.")
            return
        download_chapters_cli(client, title, selected, args.output, cbz=args.cbz)
        return

    parser.print_help()
