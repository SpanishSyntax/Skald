"""FFmpeg audio concatenation, encoding, and M4B/MP3 muxing for Skald."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence


def check_ffmpeg() -> bool:
    """Verify that ffmpeg and ffprobe are available in the PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_audio_duration_ms(path: Path) -> float:
    """Accurately query audio duration in milliseconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        dur_sec = float(res.stdout.strip())
        return dur_sec * 1000.0
    except Exception:
        # Fallback to mutagen
        try:
            from mutagen import File

            audio = File(str(path))
            if audio is not None and audio.info is not None:
                return float(audio.info.length) * 1000.0
        except Exception:
            pass
        return 0.0


def concat_audio_segments(
    segment_files: Sequence[Path],
    output_path: Path,
    concat_list_path: Path,
    reencode: bool = False,
    bitrate: str = "64k",
) -> None:
    """Concatenate audio segments using ffmpeg concat demuxer."""
    concat_lines = [f"file '{p.resolve()}'" for p in segment_files]
    concat_list_path.write_text("\n".join(concat_lines), encoding="utf-8")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
    ]

    if not reencode and output_path.suffix.lower() == ".mp3":
        cmd.extend(["-c", "copy", str(output_path)])
    elif output_path.suffix.lower() == ".m4b" or output_path.suffix.lower() == ".m4a":
        cmd.extend(["-c:a", "aac", "-b:a", bitrate, "-f", "mp4", str(output_path)])
    else:
        cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate, str(output_path)])

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)


def mux_m4b_with_chapters(
    audio_source: Path,
    ffmetadata_path: Path,
    output_m4b: Path,
    bitrate: str = "64k",
) -> None:
    """Mux audio stream and FFMETADATA chapters into a complete M4B container."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_source),
        "-i",
        str(ffmetadata_path),
        "-map_metadata",
        "1",
        "-c:a",
        "aac",
        "-b:a",
        bitrate,
        "-f",
        "mp4",
        str(output_m4b),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)


def export_mp3(
    audio_source: Path,
    output_mp3: Path,
    bitrate: str = "64k",
) -> None:
    """Export an audio source to MP3 format."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_source),
        "-c:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(output_mp3),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
