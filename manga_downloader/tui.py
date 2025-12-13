from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Tuple

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, ListItem, ListView, RichLog, Static
from textual import events, work

from .sources.base import Chapter, Manga
from .sources.registry import get_client, list_sources
from .downloader import download_chapter
from .utils import sanitize_filename


class MangaFetcherApp(App):
    TITLE = "Manga Fetcher"
    BINDINGS = [
        ("s", "set_start", "Set range start"),
        ("e", "set_end", "Set range end"),
        ("c", "clear_range", "Clear range"),
        ("enter", "download", "Download range"),
        ("escape", "command_palette", "Command palette"),
        ("space", "toggle_source", "Toggle source"),
        ("q", "quit", "Quit"),
    ]
    CSS = """
    Screen {
        layout: vertical;
    }
    .pane {
        height: 1fr;
    }
    #sources {
        height: 6;
        border: solid $primary;
        padding: 0 1;
        background: $panel;
    }
    #source_summary {
        color: $text-muted;
        height: 1;
    }
    #status {
        background: $panel;
        padding: 0 1;
        height: 1;
    }
    #log {
        display: none;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.source_name = "kisslove"
        self.client = get_client(self.source_name)
        self.mangas: List[Tuple[str, Manga]] = []
        self.chapters: List[Chapter] = []
        self.selected_manga: Optional[Manga] = None
        self.selected_manga_source: Optional[str] = None
        self.range_start: Optional[int] = None
        self.range_end: Optional[int] = None
        self.source_state: dict[str, dict[str, object]] = {}
        self.manga_cache: dict[tuple[str, str], dict[str, object]] = {}
        self.last_query: Optional[str] = None
        self.last_selected_slug: Optional[str] = None
        self.last_selected_source: Optional[str] = None
        self.last_selected_title: Optional[str] = None
        self.selected_sources: List[str] = []
        self.available_sources = list_sources()
        self._last_click_was_mouse = False
        self.status_progress: Optional[str] = None
        self.downloaded_chapters: dict[tuple[str, str], set[str]] = {}
        self.theme_mode = "dark"
        self.theme_name: Optional[str] = None
        self.state_path = Path.home() / "manga_downloader_state.json"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Sources (space to toggle)")
        yield ListView(id="sources")
        yield Static("Selected: (none)", id="source_summary")
        yield Input(placeholder="Search manga", id="search")
        with Horizontal(classes="pane"):
            with Vertical():
                yield Static("Results")
                yield ListView(id="results")
            with Vertical():
                yield Static("Chapters")
                yield ListView(id="chapters")
        yield Static("Status", id="status")
        yield RichLog(id="log")
        yield Footer()

    def on_mount(self) -> None:
        self._load_session()
        self._apply_theme()
        self.query_one("#search", Input).focus()
        if self.last_query:
            self.query_one("#search", Input).value = self.last_query
        if not self.selected_sources:
            self._select_default_sources()
        self._apply_source_selection()
        self._show_previous_selection()
        self._update_status()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self.last_query = query
        self.search_manga(query)

    def on_key(self, event: events.Key) -> None:
        if event.key != "enter":
            return
        if isinstance(self.focused, Input):
            return
        if getattr(self.focused, "id", None) == "chapters":
            event.stop()
            event.prevent_default()
            self.action_download()
            return
        self.action_download()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._last_click_was_mouse = True

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "sources":
            if self._last_click_was_mouse:
                self._last_click_was_mouse = False
                self.action_toggle_source()
            return
        if event.list_view.id == "results":
            index = event.list_view.index or 0
            if 0 <= index < len(self.mangas):
                source, manga = self.mangas[index]
                self.selected_manga_source = source
                self.selected_manga = manga
                self.source_name = source
                self.client = get_client(source)
                self.load_chapters(manga.slug)
                self._update_state()
                self._update_status()
        elif event.list_view.id == "chapters":
            if self.selected_manga and event.list_view.index is not None:
                key = (self.source_name, self.selected_manga.slug)
                cache = self.manga_cache.get(key) or {}
                cache["chapter_index"] = event.list_view.index
                self.manga_cache[key] = cache
                self._update_range_from_click(event.list_view.index)
                self._update_status()

    def action_set_start(self) -> None:
        self._set_range_from_cursor(is_start=True)

    def action_set_end(self) -> None:
        self._set_range_from_cursor(is_start=False)

    def action_clear_range(self) -> None:
        self.range_start = None
        self.range_end = None
        self._refresh_chapter_list()
        self._save_manga_cache()
        self._update_state()
        self._update_status()

    def action_download(self) -> None:
        self._set_status_progress("Preparing download")
        self.download_range()

    def action_toggle_source(self) -> None:
        sources_view = self.query_one("#sources", ListView)
        index = sources_view.index
        if index is None or index < 0 or index >= len(self.available_sources):
            return
        name = self.available_sources[index]
        if name in self.selected_sources:
            if len(self.selected_sources) > 1:
                self.selected_sources.remove(name)
        else:
            self.selected_sources.append(name)
        self._apply_source_selection()
        self._save_session()
        self._update_status()

    def _safe_call(self, func, *args) -> None:
        try:
            self.call_from_thread(func, *args)
        except RuntimeError:
            func(*args)

    def _log(self, message: str) -> None:
        self._safe_call(self._write_log, message)

    def _write_log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _set_results(self, mangas: List[Tuple[str, Manga]]) -> None:
        results = self.query_one("#results", ListView)
        results.clear()
        selected_slug = self.selected_manga.slug if self.selected_manga else self.last_selected_slug
        selected_source = self.selected_manga_source or self.last_selected_source
        for source, manga in mangas:
            marker = "*" if selected_slug == manga.slug and selected_source == source else " "
            label = f"{marker} {source.title()} · {manga.title}"
            results.append(ListItem(Static(label, markup=False)))

    def _render_sources(self) -> None:
        view = self.query_one("#sources", ListView)
        view.clear()
        for name in self.available_sources:
            checked = name in self.selected_sources
            marker = "[green]■[/green]" if checked else "[dim]□[/dim]"
            label = f"{marker} {name.title()}"
            view.append(ListItem(Static(label, markup=True)))
        self._update_source_summary()

    def _set_chapters(self, chapters: List[Chapter]) -> None:
        view = self.query_one("#chapters", ListView)
        view.clear()
        for idx, ch in enumerate(chapters, start=1):
            view.append(ListItem(Static(self._chapter_label(idx, ch), markup=True)))

    def _refresh_chapter_list(self) -> None:
        self._safe_call(self._set_chapters, self.chapters)

    def _set_range_from_cursor(self, is_start: bool) -> None:
        chapters_view = self.query_one("#chapters", ListView)
        index = chapters_view.index
        if index is None:
            return
        if is_start:
            self.range_start = index + 1
            self._log(f"Range start set to {self.range_start}")
        else:
            self.range_end = index + 1
            self._log(f"Range end set to {self.range_end}")
        self._refresh_chapter_list()
        self._save_manga_cache()
        self._update_state()

    def _update_range_from_click(self, index: int) -> None:
        if self.range_start is None:
            self.range_start = index + 1
            self._log(f"Range start set to {self.range_start}")
        elif self.range_end is None:
            self.range_end = index + 1
            self._log(f"Range end set to {self.range_end}")
        else:
            self.range_start = index + 1
            self.range_end = None
            self._log(f"Range start reset to {self.range_start}")
        self._refresh_chapter_list()
        self._save_manga_cache()
        self._update_state()

    def _chapter_label(self, index: int, chapter: Chapter) -> str:
        start = self.range_start
        end = self.range_end
        in_range = False
        if start and end:
            lo, hi = sorted((start, end))
            in_range = lo <= index <= hi
        elif start and index == start:
            in_range = True
        elif end and index == end:
            in_range = True

        prefix = "   "
        if start and index == start:
            prefix = "[S]"
        if end and index == end:
            prefix = "[E]"
        if in_range and prefix == "   ":
            prefix = "[*]"

        is_done = False
        if self.selected_manga:
            key = (self.source_name, self.selected_manga.slug)
            done = chapter.id in self.downloaded_chapters.get(key, set())
            if not done:
                done = chapter.slug in self.downloaded_chapters.get(key, set())
            if done:
                is_done = True

        num = f" ({chapter.number})" if chapter.number else ""
        label = f"{prefix} {chapter.title}{num}"
        if is_done:
            label = f"[green]{label}[/green]"
        return f"[reverse]{label}[/reverse]" if in_range else label

    def _save_state(self) -> None:
        if not self.source_name:
            return
        state: dict[str, object] = {
            "mangas": self.mangas,
            "chapters": self.chapters,
            "selected_slug": self.selected_manga.slug if self.selected_manga else None,
            "selected_source": self.selected_manga_source,
            "range_start": self.range_start,
            "range_end": self.range_end,
            "chapter_index": self.query_one("#chapters", ListView).index,
            "results_index": self.query_one("#results", ListView).index,
            "last_query": self.last_query,
            "sources": self.selected_sources,
        }
        self.source_state[self.source_name] = state
        self._save_session()

    def _update_state(self) -> None:
        self._save_state()

    def _save_manga_cache(self) -> None:
        if not self.selected_manga:
            return
        key = (self.source_name, self.selected_manga.slug)
        self.manga_cache[key] = {
            "range_start": self.range_start,
            "range_end": self.range_end,
            "chapter_index": self.query_one("#chapters", ListView).index,
        }

    def _coerce_int(self, value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value
        return None

    def _restore_state(self, source: str) -> bool:
        state = self.source_state.get(source)
        if not state:
            return False
        mangas = state.get("mangas")
        chapters = state.get("chapters")
        self.mangas = mangas if isinstance(mangas, list) else []
        self.chapters = chapters if isinstance(chapters, list) else []
        selected_slug = state.get("selected_slug")
        self.selected_manga = None
        selected_source = state.get("selected_source")
        if isinstance(selected_slug, str) and selected_slug and isinstance(selected_source, str):
            for source_name, manga in self.mangas:
                if source_name == selected_source and manga.slug == selected_slug:
                    self.selected_manga = manga
                    self.selected_manga_source = source_name
                    break
        self.range_start = self._coerce_int(state.get("range_start"))
        self.range_end = self._coerce_int(state.get("range_end"))
        if self.selected_manga:
            key = (source, self.selected_manga.slug)
            cache = self.manga_cache.get(key)
            if cache:
                self.range_start = self._coerce_int(cache.get("range_start"))
                self.range_end = self._coerce_int(cache.get("range_end"))
        self._safe_call(self._set_results, self.mangas)
        self._safe_call(self._set_chapters, self.chapters)
        results_index = self._coerce_int(state.get("results_index"))
        chapters_index = self._coerce_int(state.get("chapter_index"))
        if results_index is not None:
            self.query_one("#results", ListView).index = results_index
        if chapters_index is not None:
            self.query_one("#chapters", ListView).index = chapters_index
        return True

    @work(thread=True)
    def search_manga(self, query: str) -> None:
        self._log(f"Searching: {query}")
        sources = self.selected_sources
        if not sources:
            self._log("Select at least one source before searching")
            return
        results: List[Tuple[str, Manga]] = []
        for source in sources:
            client = get_client(source)
            for manga in client.search(query):
                results.append((source, manga))
        self.mangas = results
        self._safe_call(self._set_results, results)
        self._update_state()
        self._restore_selection_after_search()
        self._log(f"Found {len(results)} results")

    @work(thread=True)
    def load_chapters(self, slug: str) -> None:
        self._log(f"Loading chapters for {slug}")
        chapters = self.client.chapters(slug)
        self.chapters = chapters
        key = (self.source_name, slug)
        cache = self.manga_cache.get(key)
        if cache:
            self.range_start = self._coerce_int(cache.get("range_start"))
            self.range_end = self._coerce_int(cache.get("range_end"))
        else:
            self.range_start = None
            self.range_end = None
        self._sync_downloaded_from_disk()
        self._safe_call(self._set_chapters, chapters)
        chapter_index = self._coerce_int(cache.get("chapter_index")) if cache else None
        if chapter_index is not None:
            self.query_one("#chapters", ListView).index = chapter_index
        self._log(f"Loaded {len(chapters)} chapters")

    @work(thread=True)
    def download_range(self) -> None:
        if not self.selected_manga:
            self._log("Select a manga first")
            return
        if not self.chapters:
            self._log("No chapters loaded")
            return
        start = self.range_start or 1
        end = self.range_end or len(self.chapters)
        if start > end:
            start, end = end, start
        selected = self.chapters[start - 1 : end]
        out_dir = Path("downloads")
        key = (self.source_name, self.selected_manga.slug)
        downloaded = self.downloaded_chapters.setdefault(key, set())
        total_chapters = len(selected)
        for idx, chapter in enumerate(selected, start=1):
            self._safe_call(self._set_status_progress, f"Downloading {idx}/{total_chapters}: {chapter.title}")
            download_chapter(self.client, self.selected_manga.title, chapter, out_dir, log=self._log)
            downloaded.add(chapter.id)
            downloaded.add(chapter.slug)
            self._safe_call(self._refresh_chapter_list)
        self._safe_call(self._set_status_progress, "Download complete")
        self._log("Done")

    def _sync_selected_sources(self) -> None:
        if self.selected_sources:
            self.source_name = self.selected_sources[0]
            self.client = get_client(self.source_name)
        self._update_source_summary()

    def _select_default_sources(self) -> None:
        if not self.available_sources:
            return
        self.selected_sources = [self.available_sources[0]]

    def _update_source_summary(self) -> None:
        summary = "Selected: " + (", ".join(self.selected_sources) if self.selected_sources else "(none)")
        self.query_one("#source_summary", Static).update(summary)

    def _update_status(self) -> None:
        range_text = "Range: (none)"
        if self.range_start or self.range_end:
            start_idx = (self.range_start or 1) - 1
            end_idx = (self.range_end or len(self.chapters)) - 1
            if self.chapters:
                lo, hi = sorted((start_idx, end_idx))
                lo = max(0, min(lo, len(self.chapters) - 1))
                hi = max(0, min(hi, len(self.chapters) - 1))
                start_title = self.chapters[lo].title
                end_title = self.chapters[hi].title
                if lo == hi:
                    range_text = f"Range: {start_title}"
                else:
                    range_text = f"Range: {start_title} -> {end_title}"
        progress = f" | {self.status_progress}" if self.status_progress else ""
        text = f"{range_text}{progress}"
        self.query_one("#status", Static).update(text)

    def _sync_downloaded_from_disk(self) -> None:
        if not self.selected_manga:
            return
        manga_dir = Path("downloads") / sanitize_filename(self.selected_manga.title)
        if not manga_dir.exists():
            self.downloaded_chapters[(self.source_name, self.selected_manga.slug)] = set()
            return
        downloaded: set[str] = set()
        for chapter in self.chapters:
            chapter_name = sanitize_filename(chapter.title)
            chapter_dir = manga_dir / chapter_name
            cbz_path = manga_dir / f"{chapter_name}.cbz"
            if chapter_dir.exists() or cbz_path.exists():
                downloaded.add(chapter.id)
                downloaded.add(chapter.slug)
        self.downloaded_chapters[(self.source_name, self.selected_manga.slug)] = downloaded

    def _set_status_progress(self, text: Optional[str]) -> None:
        self.status_progress = text
        self._update_status()

    def _save_session(self) -> None:
        self.theme_mode = "dark" if self.theme and "dark" in self.theme else "light"
        payload = {
            "last_query": self.last_query,
            "selected_source": self.selected_manga_source,
            "selected_slug": self.selected_manga.slug if self.selected_manga else None,
            "selected_title": self.selected_manga.title if self.selected_manga else None,
            "range_start": self.range_start,
            "range_end": self.range_end,
            "sources": self.selected_sources,
            "theme": self.theme_mode,
            "theme_name": self.theme,
        }
        try:
            self.state_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def _load_session(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.last_query = payload.get("last_query") if isinstance(payload.get("last_query"), str) else None
        self.last_selected_source = (
            payload.get("selected_source") if isinstance(payload.get("selected_source"), str) else None
        )
        self.last_selected_slug = (
            payload.get("selected_slug") if isinstance(payload.get("selected_slug"), str) else None
        )
        self.last_selected_title = (
            payload.get("selected_title") if isinstance(payload.get("selected_title"), str) else None
        )
        theme = payload.get("theme") if isinstance(payload.get("theme"), str) else None
        if theme in {"dark", "light"}:
            self.theme_mode = theme
        theme_name = payload.get("theme_name") if isinstance(payload.get("theme_name"), str) else None
        if theme_name:
            self.theme_name = theme_name
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        self.selected_sources = [s for s in sources if isinstance(s, str)]

    def _apply_source_selection(self) -> None:
        self._render_sources()
        self._sync_selected_sources()

    def _apply_theme(self) -> None:
        if self.theme_name:
            self.theme = self.theme_name
            return
        self.theme = "textual-dark" if self.theme_mode == "dark" else "textual-light"

    def watch_theme(self, value: str) -> None:
        self.theme_name = value
        self._save_session()

    def _restore_selection_after_search(self) -> None:
        if not self.last_selected_slug or not self.last_selected_source:
            return
        for idx, (source, manga) in enumerate(self.mangas):
            if source == self.last_selected_source and manga.slug == self.last_selected_slug:
                self.query_one("#results", ListView).index = idx
                self.selected_manga_source = source
                self.selected_manga = manga
                self.source_name = source
                self.client = get_client(source)
                self.load_chapters(manga.slug)
                self._update_status()
                break

    def _show_previous_selection(self) -> None:
        if not self.last_selected_slug or not self.last_selected_source or not self.last_selected_title:
            return
        manga = Manga(slug=self.last_selected_slug, title=self.last_selected_title, cover=None)
        self.mangas = [(self.last_selected_source, manga)]
        self.selected_manga_source = self.last_selected_source
        self.selected_manga = manga
        self.source_name = self.last_selected_source
        self.client = get_client(self.source_name)
        self._safe_call(self._set_results, self.mangas)


def run_tui() -> None:
    MangaFetcherApp().run()
