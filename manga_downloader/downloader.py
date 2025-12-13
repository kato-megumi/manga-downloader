from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Callable, Iterable, Optional

from rich.progress import Progress, TaskID

from .sources.base import BaseClient, Chapter
from .utils import ensure_dir, guess_ext_from_url, sanitize_filename


class DownloadError(RuntimeError):
    pass


def download_chapter(
    client: BaseClient,
    manga_title: str,
    chapter: Chapter,
    output_dir: Path,
    cbz: bool = False,
    pages: Optional[list[str]] = None,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Path:
    manga_dir = ensure_dir(output_dir / sanitize_filename(manga_title))
    chapter_name = sanitize_filename(chapter.title)
    chapter_dir = ensure_dir(manga_dir / chapter_name)

    pages = pages or client.chapter_pages(chapter.id)
    if not pages:
        raise DownloadError(f"No pages found for {chapter.title}")

    for idx, url in enumerate(pages, start=1):
        ext = guess_ext_from_url(url)
        filename = f"{idx:03d}{ext}"
        dest = chapter_dir / filename
        if dest.exists():
            if progress and task_id is not None:
                progress.advance(task_id)
            continue

        resp = client.session.get(url, stream=True, timeout=client.timeout)
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)

        if progress and task_id is not None:
            progress.advance(task_id)
        if log and idx % 5 == 0:
            log(f"{chapter.title}: {idx}/{len(pages)}")

    if cbz:
        cbz_path = manga_dir / f"{chapter_name}.cbz"
        _make_cbz(chapter_dir, cbz_path)

    return chapter_dir


def download_chapters_cli(
    client: BaseClient,
    manga_title: str,
    chapters: Iterable[Chapter],
    output_dir: Path,
    cbz: bool = False,
) -> None:
    chapters = list(chapters)
    with Progress() as progress:
        for chapter in chapters:
            pages = client.chapter_pages(chapter.id)
            task_id = progress.add_task(chapter.title, total=len(pages) if pages else 0)
            download_chapter(
                client,
                manga_title,
                chapter,
                output_dir,
                cbz=cbz,
                pages=pages,
                progress=progress,
                task_id=task_id,
            )


def _make_cbz(chapter_dir: Path, cbz_path: Path) -> None:
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(chapter_dir.glob("*")):
            zf.write(path, path.name)
