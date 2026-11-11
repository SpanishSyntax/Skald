"""Neural text-to-speech synthesis engine with multi-voice support and sentence chunking for Skald."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import edge_tts

from skald.metadata import (
    build_ffmetadata,
    parse_markdown_transcript,
    tag_m4b_file,
)
from skald.muxer import (
    concat_audio_segments,
    export_mp3,
    get_audio_duration_ms,
    mux_m4b_with_chapters,
)

# Setup dedicated Skald logger
LOG_DIR = Path.home() / ".local" / "state" / "skald"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "skald.log"

logger = logging.getLogger("skald")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(fh)


@dataclass
class DialogueTurn:
    speaker: str
    voice: str
    text: str


def sanitize_speech_text(text: str) -> str:
    """Clean markdown artifacts, LaTeX, double spaces, and typography for clean neural speech."""
    t = text

    # Strip code blocks
    t = re.sub(r"```[\s\S]*?```", " [code block omitted] ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Strip block math $$...$$ and inline math $...$
    t = re.sub(r"\$\$[\s\S]*?\$\$", " [equation] ", t)
    t = re.sub(r"\$([^\$]+)\$", r"\1", t)

    # Strip markdown image and link formatting [label](url) -> label
    t = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)

    # Strip HTML tags
    t = re.sub(r"<[^>]+>", "", t)

    # Normalize typographic quotes and dashes
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("—", ", ").replace("–", ", ")

    # Strip bullet stars and markdown headers markers inside body
    t = re.sub(r"^\s*[*+-]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*#{1,6}\s+", "", t, flags=re.MULTILINE)

    # Strip markdown bold/italics markers **text** or *text*
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)

    # Collapse multiple spaces and tabs into a single space
    t = re.sub(r"[ \t]+", " ", t)

    # Collapse multiple blank lines
    t = re.sub(r"\n\s*\n", "\n\n", t)

    return t.strip()


def chunk_text(text: str, max_chars: int = 2500) -> list[str]:
    """Split long text at sentence boundaries to strictly prevent Azure TTS payload limits."""
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

        # If a single sentence exceeds max_chars, split on clauses or commas
        if len(s_clean) > max_chars:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0
            sub_clauses = re.split(r"(?<=[,;:])\s+", s_clean)
            for sc in sub_clauses:
                if current_len + len(sc) + 1 > max_chars and current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [sc]
                    current_len = len(sc)
                else:
                    current_chunk.append(sc)
                    current_len += len(sc) + 1
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


def parse_multivoice_turns(
    text: str,
    default_voice: str,
    speaker_map: dict[str, str] | None = None,
) -> list[DialogueTurn]:
    """Parse a section's text into dialogue turns according to speaker markers."""
    mapping = speaker_map or {}
    lines = text.split("\n\n")
    turns: list[DialogueTurn] = []

    # Pattern for explicit speaker tags: **Alice:** or [Speaker: Alice] or Alice:
    speaker_tag_pattern = re.compile(
        r"^(?:\*\*([A-Za-z0-9_ -]+):\*\*|\[Speaker:\s*([A-Za-z0-9_ -]+)\]|([A-Za-z0-9_ -]+):\s+)(.*)$",
        re.DOTALL,
    )

    current_speaker = "Narrator"
    current_voice = mapping.get("Narrator", default_voice)

    for para in lines:
        p_clean = para.strip()
        if not p_clean:
            continue

        m = speaker_tag_pattern.match(p_clean)
        if m:
            spk_name = m.group(1) or m.group(2) or m.group(3)
            spk_name = spk_name.strip()
            body = m.group(4).strip()
            voice = mapping.get(spk_name, default_voice)
            current_speaker = spk_name
            current_voice = voice
            if body:
                turns.append(
                    DialogueTurn(
                        speaker=current_speaker, voice=current_voice, text=body
                    )
                )
        else:
            turns.append(
                DialogueTurn(speaker=current_speaker, voice=current_voice, text=p_clean)
            )

    if not turns and text.strip():
        turns.append(
            DialogueTurn(speaker="Narrator", voice=default_voice, text=text.strip())
        )

    return turns


async def synthesize_chunk_with_retry(
    text: str,
    output_path: Path,
    voice: str = "en-US-GuyNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    max_retries: int = 5,
    timeout_sec: float = 45.0,
) -> bool:
    """Synthesize a text chunk with resilience against server refusals, timeouts, and rate limits."""
    logger.debug(
        "Synthesizing chunk (%d chars) with voice %s -> %s",
        len(text),
        voice,
        output_path.name,
    )
    for attempt in range(1, max_retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            await asyncio.wait_for(
                communicate.save(str(output_path)), timeout=timeout_sec
            )
            if output_path.exists() and output_path.stat().st_size > 500:
                logger.debug(
                    "Chunk %s successfully synthesized on attempt %d",
                    output_path.name,
                    attempt,
                )
                return True
            else:
                logger.warning(
                    "Chunk %s output file too small (<500B), retrying...",
                    output_path.name,
                )
        except asyncio.TimeoutError:
            logger.warning(
                "TTS timeout (%0.1fs) on attempt %d for chunk %s",
                timeout_sec,
                attempt,
                output_path.name,
            )
        except Exception as e:
            logger.warning(
                "TTS error on attempt %d for chunk %s: %s", attempt, output_path.name, e
            )

        if attempt < max_retries:
            backoff = 2.0 * attempt
            logger.info("Backing off for %0.1fs before retry...", backoff)
            await asyncio.sleep(backoff)

    logger.error(
        "Failed to synthesize chunk %s after %d retries.", output_path.name, max_retries
    )
    raise RuntimeError(
        f"Edge-TTS failed to synthesize chunk after {max_retries} attempts."
    )


async def synthesize_transcript(
    transcript_path: Path,
    output_dir: Path,
    voice: str = "en-US-GuyNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Synthesize a markdown transcript with multi-voice support and sentence chunking into M4B & MP3."""
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / f"temp_{transcript_path.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    text_content = transcript_path.read_text(encoding="utf-8")
    meta, sections = parse_markdown_transcript(text_content)

    title = meta.get("title", transcript_path.stem.replace("_", " ").title())
    author = meta.get("author", "Skald Companion")
    album = meta.get("album", "Course Lecture Companion")

    # Frontmatter voice or speaker overrides
    doc_voice = meta.get("voice", voice)
    speaker_map: dict[str, str] = {}
    if "narrator" in meta:
        speaker_map["Narrator"] = meta["narrator"]
    for k, v in meta.items():
        if k.startswith("speaker_") or k.startswith("voice_"):
            spk = k.split("_", 1)[1].title()
            speaker_map[spk] = v

    m4b_path = output_dir / f"{transcript_path.stem}.m4b"
    mp3_path = output_dir / f"{transcript_path.stem}.mp3"

    section_files: list[Path] = []
    total_sections = len(sections)

    from skald.metadata import ChapterInfo

    chapters: list[ChapterInfo] = []
    current_time_ms = 0.0

    for idx, sec in enumerate(sections, 1):
        if progress_callback:
            progress_callback(
                f"Synthesizing section {idx}/{total_sections}: {sec.title}",
                idx,
                total_sections,
            )

        turns = parse_multivoice_turns(
            sec.text, default_voice=doc_voice, speaker_map=speaker_map
        )
        chunk_files: list[Path] = []
        c_counter = 0

        for turn in turns:
            cleaned_text = sanitize_speech_text(turn.text)
            chunks = chunk_text(cleaned_text, max_chars=2500)

            for chunk in chunks:
                c_counter += 1
                chunk_file = temp_dir / f"sec_{idx:03d}_part_{c_counter:03d}.mp3"
                await synthesize_chunk_with_retry(
                    chunk,
                    chunk_file,
                    voice=turn.voice,
                    rate=rate,
                    volume=volume,
                )
                chunk_files.append(chunk_file)

        # Merge section chunks
        sec_merged = temp_dir / f"section_{idx:03d}.mp3"
        concat_list = temp_dir / f"concat_{idx:03d}.txt"
        concat_audio_segments(chunk_files, sec_merged, concat_list, reencode=False)
        section_files.append(sec_merged)

        # Duration of section
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
    concat_audio_segments(
        section_files, full_mp3_temp, full_concat_list, reencode=False
    )

    # Build FFMETADATA
    ffmeta_path = temp_dir / "ffmetadata.txt"
    ffmeta_content = build_ffmetadata(chapters, title=title, author=author, album=album)
    ffmeta_path.write_text(ffmeta_content, encoding="utf-8")

    # Mux M4B with chapters
    mux_m4b_with_chapters(full_mp3_temp, ffmeta_path, m4b_path)
    tag_m4b_file(m4b_path, title=title, author=author, album=album)

    # Export MP3
    export_mp3(full_mp3_temp, mp3_path)

    # Clean up temp
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)

    logger.info(
        "Successfully compiled audiobook: %s (%s)", m4b_path.name, mp3_path.name
    )
    return m4b_path, mp3_path
