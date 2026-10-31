"""Neural text-to-speech synthesis engine with sentence chunking and resilience for Skald."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Callable, Sequence

import edge_tts

from skald.metadata import SectionMarker, build_ffmetadata, parse_markdown_transcript, tag_m4b_file
from skald.muxer import concat_audio_segments, export_mp3, get_audio_duration_ms, mux_m4b_with_chapters


def sanitize_speech_text(text: str) -> str:
    """Clean markdown artifacts, special characters, and math syntax for clear oral speech."""
    t = text
    # Remove code blocks or math blocks
    t = re.sub(r"```[\s\S]*?```", " [code block omitted] ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    # Strip inline latex math syntax $x$ -> x
    t = re.sub(r"\$([^\$]+)\$", r"\1", t)
    # Remove markdown link formatting [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    # Normalize unicode quotes
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("—", " - ").replace("–", " - ")
    # Strip bullet stars
    t = re.sub(r"^\s*[*+-]\s+", "", t, flags=re.MULTILINE)
    return t.strip()


def chunk_text(text: str, max_chars: int = 2500) -> list[str]:
    """Split long section text at sentence boundaries to prevent TTS websocket timeouts."""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        if current_len + len(s_clean) + 1 > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [s_clean]
            current_len = len(s_clean)
        else:
            current_chunk.append(s_clean)
            current_len += len(s_clean) + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


async def synthesize_chunk_with_retry(
    text: str,
    output_path: Path,
    voice: str = "en-US-GuyNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    max_retries: int = 4,
    timeout_sec: float = 45.0,
) -> bool:
    """Synthesize a single text chunk with exponential backoff and timeout protection."""
    for attempt in range(1, max_retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            await asyncio.wait_for(communicate.save(str(output_path)), timeout=timeout_sec)
            if output_path.exists() and output_path.stat().st_size > 500:
                return True
        except Exception as e:
            if attempt == max_retries:
                raise RuntimeError(f"TTS synthesis failed for chunk after {max_retries} attempts: {e}")
            await asyncio.sleep(1.5 * attempt)
    return False


async def synthesize_transcript(
    transcript_path: Path,
    output_dir: Path,
    voice: str = "en-US-GuyNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Synthesize a full markdown transcript into both an M4B audiobook and an MP3 file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / f"temp_{transcript_path.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    text_content = transcript_path.read_text(encoding="utf-8")
    meta, sections = parse_markdown_transcript(text_content)

    title = meta.get("title", transcript_path.stem.replace("_", " ").title())
    author = meta.get("author", "Skald Companion")
    album = meta.get("album", "Course Lecture Companion")

    m4b_path = output_dir / f"{transcript_path.stem}.m4b"
    mp3_path = output_dir / f"{transcript_path.stem}.mp3"

    section_files: list[Path] = []
    total_sections = len(sections)

    from skald.metadata import ChapterInfo

    chapters: list[ChapterInfo] = []
    current_time_ms = 0.0

    for idx, sec in enumerate(sections, 1):
        if progress_callback:
            progress_callback(f"Synthesizing section {idx}/{total_sections}: {sec.title}", idx, total_sections)

        cleaned_text = sanitize_speech_text(sec.text)
        chunks = chunk_text(cleaned_text, max_chars=2500)
        chunk_files: list[Path] = []

        for c_idx, chunk in enumerate(chunks, 1):
            chunk_file = temp_dir / f"sec_{idx:03d}_part_{c_idx:02d}.mp3"
            await synthesize_chunk_with_retry(
                chunk,
                chunk_file,
                voice=voice,
                rate=rate,
                volume=volume,
            )
            chunk_files.append(chunk_file)

        # Merge section chunks
        sec_merged = temp_dir / f"section_{idx:03d}.mp3"
        concat_list = temp_dir / f"concat_{idx:03d}.txt"
        concat_audio_segments(chunk_files, sec_merged, concat_list, reencode=False)
        section_files.append(sec_merged)

        # Duration of this section
        sec_dur_ms = get_audio_duration_ms(sec_merged)
        start_ms = current_time_ms
        end_ms = current_time_ms + sec_dur_ms
        current_time_ms = end_ms

        chapters.append(
            ChapterInfo(
                number=idx,
                title=sec.title,
                start_ms=start_ms,
                end_ms=end_ms,
                total_duration_ms=int(sec_dur_ms),
            )
        )

    # Concat all sections into unified MP3
    full_mp3_temp = temp_dir / "full_audio.mp3"
    full_concat_list = temp_dir / "full_concat.txt"
    concat_audio_segments(section_files, full_mp3_temp, full_concat_list, reencode=False)

    # Write FFMETADATA
    ffmeta_path = temp_dir / "ffmetadata.txt"
    ffmeta_content = build_ffmetadata(chapters, title=title, author=author, album=album)
    ffmeta_path.write_text(ffmeta_content, encoding="utf-8")

    # Mux M4B with chapters
    mux_m4b_with_chapters(full_mp3_temp, ffmeta_path, m4b_path)
    tag_m4b_file(m4b_path, title=title, author=author, album=album)

    # Copy / convert final MP3
    export_mp3(full_mp3_temp, mp3_path)

    # Clean up temp
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    return m4b_path, mp3_path
