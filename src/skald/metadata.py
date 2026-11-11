"""Audiobook chapter metadata and tagging engine for Skald."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


@dataclass
class SectionMarker:
    title: str
    text: str
    duration_ms: int = 0
    start_ms: int = 0
    end_ms: int = 0


@dataclass
class ChapterInfo:
    number: int
    title: str
    sections: list[SectionMarker] = field(default_factory=list)
    total_duration_ms: int = 0
    start_ms: int = 0
    end_ms: int = 0
    audio_path: Path | None = None


def sanitize_title(title: str) -> str:
    """Sanitize section and chapter titles for ffmpeg metadata and filenames."""
    t = re.sub(r"[#*`_]", "", title).strip()
    # Normalize fancy punctuation
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return t


def parse_markdown_transcript(
    md_text: str,
) -> tuple[dict[str, str], list[SectionMarker]]:
    """Parse a markdown companion transcript into header metadata and sections."""
    lines = md_text.splitlines()
    metadata: dict[str, str] = {}
    sections: list[SectionMarker] = []

    current_title = "Introduction"
    current_lines: list[str] = []

    # Check for YAML-like or frontmatter headers
    in_frontmatter = False
    idx = 0

    if lines and lines[0].strip() == "---":
        in_frontmatter = True
        idx = 1
        while idx < len(lines):
            line = lines[idx]
            if line.strip() == "---":
                idx += 1
                break
            if ":" in line:
                k, v = line.split(":", 1)
                metadata[k.strip().lower()] = v.strip().strip('"').strip("'")
            idx += 1

    for line in lines[idx:]:
        h_match = re.match(r"^(#{1,3})\s+(.*)$", line)
        if h_match:
            heading_level = len(h_match.group(1))
            heading_text = sanitize_title(h_match.group(2))

            if heading_level == 1 and not metadata.get("title"):
                metadata["title"] = heading_text

            if current_lines:
                text_block = "\n".join(current_lines).strip()
                if text_block:
                    sections.append(SectionMarker(title=current_title, text=text_block))
                current_lines = []

            current_title = heading_text
        else:
            current_lines.append(line)

    if current_lines:
        text_block = "\n".join(current_lines).strip()
        if text_block:
            sections.append(SectionMarker(title=current_title, text=text_block))

    return metadata, sections


def build_ffmetadata(
    chapters: Sequence[ChapterInfo],
    title: str = "Audiobook Companion",
    author: str = "Skald Narrator",
    album: str = "Course Audio Companion",
    genre: str = "Audiobook",
) -> str:
    """Generate standard FFMETADATA1 syntax with embedded chapter timestamps."""
    ff_lines = [
        ";FFMETADATA1",
        f"title={sanitize_title(title)}",
        f"artist={sanitize_title(author)}",
        f"album={sanitize_title(album)}",
        f"genre={sanitize_title(genre)}",
        "",
    ]

    for chap in chapters:
        # Timebase is 1/1000 (milliseconds)
        ff_lines.append("[CHAPTER]")
        ff_lines.append("TIMEBASE=1/1000")
        ff_lines.append(f"START={int(chap.start_ms)}")
        ff_lines.append(f"END={int(chap.end_ms)}")
        ff_lines.append(f"title={sanitize_title(chap.title)}")
        ff_lines.append("")

    return "\n".join(ff_lines)


def tag_m4b_file(
    m4b_path: Path,
    title: str,
    author: str,
    album: str | None = None,
    genre: str = "Audiobook",
    track_number: int | None = None,
    total_tracks: int | None = None,
    cover_image: Path | None = None,
) -> None:
    """Apply iTunes/QuickTime MP4 metadata tags to an M4B file."""
    try:
        from mutagen.mp4 import MP4, MP4Cover
    except ImportError:
        return

    audio = MP4(str(m4b_path))
    audio["\xa9nam"] = [title]
    audio["\xa9ART"] = [author]
    if album:
        audio["\xa9alb"] = [album]
    audio["\xa9gen"] = [genre]
    audio["stik"] = [2]  # 2 = Audiobook

    if track_number is not None:
        tot = total_tracks or track_number
        audio["trkn"] = [(track_number, tot)]

    if cover_image and cover_image.is_file():
        data = cover_image.read_bytes()
        image_format = (
            MP4Cover.FORMAT_PNG
            if cover_image.suffix.lower() == ".png"
            else MP4Cover.FORMAT_JPEG
        )
        audio["covr"] = [MP4Cover(data, image_format=image_format)]

    audio.save()


def read_audiobook_metadata(m4b_path: Path) -> dict[str, Any]:
    """Inspect and return metadata and chapter markers from an M4B file."""
    info: dict[str, Any] = {
        "title": "Unknown",
        "artist": "Unknown",
        "album": "Unknown",
        "duration": 0.0,
        "bitrate": 0,
        "chapters": [],
    }

    try:
        from mutagen.mp4 import MP4

        audio = MP4(str(m4b_path))
        info["duration"] = audio.info.length
        info["bitrate"] = audio.info.bitrate

        if "\xa9nam" in audio:
            info["title"] = audio["\xa9nam"][0]
        if "\xa9ART" in audio:
            info["artist"] = audio["\xa9ART"][0]
        if "\xa9alb" in audio:
            info["album"] = audio["\xa9alb"][0]
    except Exception:
        pass

    return info
