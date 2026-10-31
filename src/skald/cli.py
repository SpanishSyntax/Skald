"""Command-line interface and argument router for Skald."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from skald import __version__
from skald.metadata import read_audiobook_metadata
from skald.muxer import check_ffmpeg
from skald.stitcher import discover_chapter_files, stitch_audiobook
from skald.synthesizer import synthesize_transcript
from skald.ui import add_color_args, handle_color_args, handle_version_arg, render_error_panel, render_panel, ui
from skald.voices import RECOMMENDED_VOICES, query_voices


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS string."""
    mins, secs = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def cmd_voices(args: argparse.Namespace) -> int:
    """List available neural voices."""
    ui.info("Querying neural speech voices from Microsoft Azure / Edge-TTS...")
    try:
        voices = asyncio.run(query_voices(args.locale, args.gender))
    except Exception as e:
        render_error_panel("Voice Discovery Failed", str(e))
        return 1

    lines = [
        f"{ui.bold('Short Name'):<30} {ui.bold('Locale'):<10} {ui.bold('Gender'):<8} {ui.bold('Description')}",
        "─" * 74,
    ]

    for v in voices[:args.limit]:
        lines.append(f"{v['name']:<30} {v['locale']:<10} {v['gender']:<8} {v['friendly'][:24]}")

    if len(voices) > args.limit:
        lines.append(ui.dim(f"... and {len(voices) - args.limit} more voices (use --limit to show more)"))

    lines.append("")
    lines.append(ui.bold_cyan("Recommended Arctic Narrators:"))
    for k, v in RECOMMENDED_VOICES.items():
        lines.append(f"  • {ui.bold(k)}: {v['short_name']} ({v['gender']}) - {v['description']}")

    render_panel("Skald Neural Voices", lines, border_color="0;36")
    return 0


def cmd_narrate(args: argparse.Namespace) -> int:
    """Synthesize a markdown transcript into standalone M4B/MP3 audiobooks."""
    if not check_ffmpeg():
        render_error_panel("Missing Dependency", "ffmpeg and ffprobe must be installed and in PATH.")
        return 1

    transcript_file = Path(args.transcript).resolve()
    if not transcript_file.is_file():
        render_error_panel("File Not Found", f"Transcript file does not exist: {transcript_file}")
        return 1

    out_dir = Path(args.output_dir).resolve() if args.output_dir else transcript_file.parent

    ui.info(f"Synthesizing transcript: {ui.bold(transcript_file.name)}")
    ui.info(f"Voice: {ui.cyan(args.voice)} | Rate: {args.rate}")

    def progress(msg: str, current: int, total: int) -> None:
        pct = (current / total) * 100
        print(f"  {ui.badge()} [{pct:5.1f}%] {msg}", flush=True)

    try:
        m4b_path, mp3_path = asyncio.run(
            synthesize_transcript(
                transcript_path=transcript_file,
                output_dir=out_dir,
                voice=args.voice,
                rate=args.rate,
                progress_callback=progress,
            )
        )
    except Exception as e:
        render_error_panel("Synthesis Failed", str(e))
        return 1

    m4b_size_mb = m4b_path.stat().st_size / (1024 * 1024)
    lines = [
        f"M4B Audiobook: {ui.bold_green(m4b_path.name)} ({m4b_size_mb:.2f} MB)",
        f"MP3 Audio:     {ui.bold_green(mp3_path.name)}",
        f"Directory:     {m4b_path.parent}",
    ]
    render_panel("Narrative Synthesis Complete", lines, border_color="0;32")
    return 0


def cmd_stitch(args: argparse.Namespace) -> int:
    """Stitch multiple chapter audio files into a unified master M4B audiobook."""
    if not check_ffmpeg():
        render_error_panel("Missing Dependency", "ffmpeg and ffprobe must be installed and in PATH.")
        return 1

    # Discover inputs
    input_paths: list[Path] = []
    for item in args.inputs:
        p = Path(item).resolve()
        if p.is_dir():
            input_paths.extend(discover_chapter_files(p, extension=args.ext))
        elif p.is_file():
            input_paths.append(p)

    if not input_paths:
        render_error_panel("No Chapter Files", "No matching audio files found to stitch.")
        return 1

    output_m4b = Path(args.output).resolve()
    output_mp3 = output_m4b.with_suffix(".mp3") if args.mp3 else None
    cover_path = Path(args.cover).resolve() if args.cover else None

    ui.info(f"Stitching {len(input_paths)} chapter files into {ui.bold_cyan(output_m4b.name)}...")

    def progress(msg: str, current: int, total: int) -> None:
        pct = (current / total) * 100
        print(f"  {ui.badge()} [{pct:5.1f}%] {msg}", flush=True)

    try:
        m4b_res, mp3_res = stitch_audiobook(
            chapter_files=input_paths,
            output_m4b=output_m4b,
            output_mp3=output_mp3,
            title=args.title,
            author=args.author,
            album=args.album,
            cover_image=cover_path,
            progress_callback=progress,
        )
    except Exception as e:
        render_error_panel("Stitching Failed", str(e))
        return 1

    m4b_size_mb = m4b_res.stat().st_size / (1024 * 1024)
    lines = [
        f"Master Audiobook: {ui.bold_green(m4b_res.name)} ({m4b_size_mb:.2f} MB)",
        f"Total Chapters:   {len(input_paths)}",
        f"Author:           {args.author}",
        f"Album/Course:     {args.album}",
    ]
    if mp3_res:
        lines.append(f"Master MP3:       {ui.bold_green(mp3_res.name)}")

    render_panel("Master Audiobook Stitched", lines, border_color="0;32")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Inspect metadata and chapter structure of an M4B file."""
    m4b_file = Path(args.file).resolve()
    if not m4b_file.is_file():
        render_error_panel("File Not Found", f"Audiobook file does not exist: {m4b_file}")
        return 1

    meta = read_audiobook_metadata(m4b_file)
    dur_str = format_duration(meta["duration"])
    size_mb = m4b_file.stat().st_size / (1024 * 1024)

    lines = [
        f"File:     {ui.bold(m4b_file.name)} ({size_mb:.2f} MB)",
        f"Title:    {meta['title']}",
        f"Artist:   {meta['artist']}",
        f"Album:    {meta['album']}",
        f"Duration: {ui.bold_cyan(dur_str)}",
        f"Bitrate:  {meta['bitrate']} bps",
    ]
    render_panel("Audiobook Inspection", lines, border_color="0;36")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skald",
        description="Arctic oral companion & multi-chapter M4B audiobook compiler.",
    )
    handle_version_arg(parser, __version__)
    add_color_args(parser)

    subparsers = parser.add_subparsers(dest="subcommand", help="Skald subcommands")

    # narrate
    p_narrate = subparsers.add_parser("narrate", aliases=["recite"], help="Synthesize a markdown transcript")
    p_narrate.add_argument("transcript", help="Path to markdown transcript file")
    p_narrate.add_argument("--voice", default="en-US-GuyNeural", help="Neural TTS voice (default: en-US-GuyNeural)")
    p_narrate.add_argument("--rate", default="+0%", help="Speech rate adjustment (e.g. +5%%, -10%%)")
    p_narrate.add_argument("--output-dir", "-o", help="Target output directory")

    # stitch
    p_stitch = subparsers.add_parser("stitch", help="Stitch multiple chapters into master M4B")
    p_stitch.add_argument("inputs", nargs="+", help="Directory or chapter audio files to stitch")
    p_stitch.add_argument("--output", "-o", default="Master_Audiobook.m4b", help="Output M4B filename")
    p_stitch.add_argument("--title", default="Master Course Companion", help="Audiobook title")
    p_stitch.add_argument("--author", default="Skald Narrator", help="Audiobook author")
    p_stitch.add_argument("--album", default="Course Audio Companion", help="Album / series title")
    p_stitch.add_argument("--cover", help="Cover art image (PNG or JPG)")
    p_stitch.add_argument("--ext", default=".m4b", help="File extension to scan when directory given (.m4b or .mp3)")
    p_stitch.add_argument("--mp3", action="store_true", help="Also generate stitched MP3")

    # voices
    p_voices = subparsers.add_parser("voices", help="Query and list available neural voices")
    p_voices.add_argument("--locale", "-l", help="Filter by locale code (e.g. en-US, nl-NL)")
    p_voices.add_argument("--gender", "-g", help="Filter by gender (Male or Female)")
    p_voices.add_argument("--limit", type=int, default=25, help="Maximum voices to display (default: 25)")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect M4B metadata and chapters")
    p_inspect.add_argument("file", help="Path to M4B audiobook file")

    args = parser.parse_args(argv)
    handle_color_args(args)

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand in ("narrate", "recite"):
        return cmd_narrate(args)
    elif args.subcommand == "stitch":
        return cmd_stitch(args)
    elif args.subcommand == "voices":
        return cmd_voices(args)
    elif args.subcommand == "inspect":
        return cmd_inspect(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
