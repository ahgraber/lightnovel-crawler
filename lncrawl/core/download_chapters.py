"""
To download chapter bodies
"""

import json
import logging
from pathlib import Path
from threading import Event
from typing import Any, Optional
from ..models.chapter import Chapter
from .arguments import get_args

logger = logging.getLogger(__name__)


def get_chapter_file(
    chapter: Chapter,
    output_path: str,
    pack_by_volume: bool,
):
    dir_name = Path(output_path) / "json"
    if pack_by_volume:
        vol_name = "Volume " + str(chapter.volume).rjust(2, "0")
        dir_name = dir_name / vol_name

    chapter_name = str(chapter.id).rjust(5, "0")
    json_file = dir_name / (chapter_name + ".json")
    return json_file


def _save_chapter(file_name: Path, chapter: Chapter) -> Path:
    if not chapter.body:
        chapter.body = "<p><i>Failed to download chapter body</i></p>"

    args = get_args()
    source_notice = (
        f'<br><p><small>Source: <a href="{chapter.url}">{chapter.url}</a></small></p>'
    )
    if args.add_source_url and not chapter.body.endswith(source_notice):
        chapter.body += source_notice

    title = chapter.title
    title = "&lt;".join(title.split("<"))
    title = "&gt;".join(title.split(">"))
    title = f"<h1>{title}</h1>"
    if not chapter.body.startswith(title):
        chapter.body = "".join([title, chapter.body])

    file_name.parent.mkdir(parents=True, exist_ok=True)
    with file_name.open("w", encoding="utf-8") as fp:
        json.dump(chapter, fp, ensure_ascii=False)

    chapter.body = None
    return file_name


def _chapter_ref_for_log(chapter: Chapter) -> str:
    chapter_id = getattr(chapter, "id", None)
    chapter_title = getattr(chapter, "title", None)
    if chapter_title and chapter_id is not None:
        return f"{chapter_title} (id={chapter_id})"
    if chapter_title:
        return chapter_title
    if chapter_id is not None:
        return f"id={chapter_id}"
    return "unknown chapter"


def _set_chapter_body(chapter: Any, value: Optional[str]) -> None:
    """Assign the provided body value to a chapter-like object."""

    if hasattr(chapter, "__setitem__"):
        try:
            chapter["body"] = value
        except (TypeError, KeyError):
            # Fallback to attribute assignment only if mapping assignment fails.
            pass

    try:
        chapter.body = value
    except AttributeError:
        # Some dict-like objects (e.g. plain ``dict``) do not support attribute assignment.
        pass


def load_chapter_body_from_cache(
    chapter: Chapter, cache_file: Optional[Path]
) -> Optional[str]:
    chapter_ref = _chapter_ref_for_log(chapter)
    body = None
    if hasattr(chapter, "get"):
        body = chapter.get("body")
    if not body:
        body = getattr(chapter, "body", None)
    if body:
        _set_chapter_body(chapter, body)
        return body

    if not cache_file:
        return None

    try:
        with cache_file.open("r", encoding="utf-8") as file:
            cached_data: Any = json.load(file)
    except FileNotFoundError:
        logger.warning(
            "Chapter cache missing for %s at %s", chapter_ref, cache_file
        )
        return None
    except json.JSONDecodeError:
        logger.warning(
            "Invalid chapter cache for %s at %s", chapter_ref, cache_file
        )
        return None
    except OSError as exc:
        logger.warning(
            "Failed to read chapter cache for %s at %s: %s",
            chapter_ref,
            cache_file,
            exc,
        )
        return None

    if not isinstance(cached_data, dict):
        logger.warning(
            "Chapter cache for %s at %s did not contain a JSON object",
            chapter_ref,
            cache_file,
        )
        return None

    body = cached_data.get("body")
    if body:
        _set_chapter_body(chapter, body)

    cached_images = cached_data.get("images")
    if cached_images and hasattr(chapter, "get") and not chapter.get("images"):
        chapter["images"] = cached_images

    return body


def restore_chapter_body(app):
    from .app import App
    assert isinstance(app, App) and app.crawler, 'Invalid app instance'

    app.rebuild_chapter_cache_registry()

    restored = 0
    for chapter in app.chapters:
        file_name = app.get_chapter_cache_file(chapter)
        if not file_name:
            continue

        if not file_name.is_file():
            continue

        try:
            with file_name.open("r", encoding="utf-8") as file:
                cached_chapter = json.load(file)
        except json.JSONDecodeError:
            logger.debug("Unable to decode JSON from the file: %s", file_name)
            continue
        except Exception:  # pragma: no cover - unexpected failure
            logger.exception(
                "An error occurred while reading the file: %s", file_name
            )
            continue

        chapter.update(**cached_chapter)
        app.register_chapter_cache_file(chapter, file_name)

        if chapter.success:
            restored += 1
            chapter.body = None

    logger.info(f"Restored {restored}/{len(app.chapters)} chapters")


def fetch_chapter_body(app, signal=Event()):
    from .app import App
    assert isinstance(app, App) and app.crawler, 'Invalid app instance'

    if not app.chapters:
        return

    # attempt to restore from file cache
    restore_chapter_body(app)

    # remaining chapters
    pending_chapters = [
        chapter for chapter in app.chapters
        if not chapter.success
    ]

    # download remaining
    current = len(app.chapters) - len(pending_chapters)
    app.fetch_chapter_progress = 100 * current / len(app.chapters)
    for chapter in app.crawler.download_chapters(pending_chapters, signal=signal):
        if chapter:
            file_path = app.get_chapter_cache_file(chapter)
            if file_path is None:
                file_path = app.register_chapter_cache_file(chapter)
            saved_path = _save_chapter(file_path, chapter)
            app.register_chapter_cache_file(chapter, saved_path)
        current += 1
        app.fetch_chapter_progress = 100 * current / len(app.chapters)
        yield
    logger.info(f"Downloaded {len(pending_chapters)} chapters")
