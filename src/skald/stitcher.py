"""Multi-chapter audiobook stitcher and master M4B compiler for Skald."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable, Sequence

from skald.discovery import natural_sort_key, resolve_ordered_chapters
from skald.metadata import ChapterInfo, build_ffmetadata, tag_m4b_file
from skald.muxer import concat_audio_segments, export_mp3, get_audio_duration_ms, mux_m4b_with_chapters


def discover_chapter_files(source_dir: Path, extension: str = ".m4b") -> list[Path]:
    """Find and order chapter files using manifest declaration or natural sort."""
    _, files = resolve_ordered_chapters(source_dir, extension=extension)
    return files


def stitch_audiobook(
    chapter_files: Sequence[Path],
    output_m4b: Path,
    output_mp3: Path | None = None,
    title: str = "Master Course Companion",
    author: str = "Skald Narrator",
    album: str = "Course Audio Companion",
    cover_image: Path | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> tuple[Path, Path | None]:
    """Stitch multiple chapter audio files into a unified master M4B audiobook with chapter markers."""
    temp_dir = output_m4b.parent / f"temp_stitch_{output_m4b.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    chapters: list[ChapterInfo] = []
    current_time_ms = 0.0
    total = len(chapter_files)

    for idx, chap_file in enumerate(chapter_files, 1):
        if progress_callback:
            progress_callback(f"Indexing chapter {idx}/{total}: {chap_file.name}", idx, total)

        dur_ms = get_audio_duration_ms(chap_file)
        clean_title = chap_file.stem.replace("_", " ").title()
        # Clean generic ch01_ / chapter_01_ prefixes if present
        clean_title = re.sub(r"^(Ch\d+[\s_-]*|Chapter[\s_-]*\d+[\s_-]*)", "", clean_title, flags=re.IGNORECASE).strip()
        display_title = f"Chapter {idx:02d}: {clean_title}" if clean_title else f"Chapter {idx:02d}"

        start_ms = current_time_ms
        end_ms = current_time_ms + dur_ms
        current_time_ms = end_ms

        chapters.append(
            ChapterInfo(
                number=idx,
                title=display_title,
                start_ms=start_ms,
                end_ms=end_ms,
                total_duration_ms=int(dur_ms),
                audio_path=chap_file,
            )
        )

    # Concat all chapters
    stitched_raw = temp_dir / "stitched_raw.mp3"
    concat_list = temp_dir / "concat_list.txt"
    concat_audio_segments(chapter_files, stitched_raw, concat_list, reencode=False)

    # Build FFMETADATA
    ffmeta_path = temp_dir / "ffmetadata.txt"
    ffmeta_content = build_ffmetadata(chapters, title=title, author=author, album=album)
    ffmeta_path.write_text(ffmeta_content, encoding="utf-8")

    # Mux M4B
    mux_m4b_with_chapters(stitched_raw, ffmeta_path, output_m4b)
    tag_m4b_file(
        output_m4b,
        title=title,
        author=author,
        album=album,
        cover_image=cover_image,
    )

    # Export MP3 if requested
    if output_mp3:
        export_mp3(stitched_raw, output_mp3)

    shutil.rmtree(temp_dir, ignore_errors=True)
    return output_m4b, output_mp3
