"""Command-line interface, argument router, and MCP runner for Skald."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from skald import __version__
from skald.discovery import resolve_ordered_chapters
from skald.mcp import StdioMCPServer
from skald.metadata import read_audiobook_metadata
from skald.muxer import check_ffmpeg
from skald.stitcher import discover_chapter_files, stitch_audiobook
from skald.synthesizer import synthesize_transcript
from skald.ui import (
    add_agent_args,
    add_color_args,
    handle_agent_args,
    handle_color_args,
    handle_version_arg,
    render_error_panel,
    render_panel,
    ui,
)
from skald.voices import RECOMMENDED_VOICES, query_voices

try:
    from prism.toon import encode_toon
except ImportError:
    encode_toon = None  # type: ignore


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS string."""
    mins, secs = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def output_structured_data(data: dict[str, Any], args: argparse.Namespace) -> int:
    """Render machine-readable output in JSON or TOON format when requested."""
    is_json = getattr(args, "json", False) or getattr(ui, "is_json", False)
    is_agent = getattr(args, "agent", False) or getattr(ui, "is_agent", False) or getattr(args, "client", False)

    if is_json:
        if hasattr(ui, "json"):
            ui.json(data)
        else:
            print(json.dumps(data, indent=2))
        return 0

    if (is_agent or getattr(args, "toon", False)) and encode_toon is not None:
        print(encode_toon(data))
        return 0

    return -1


def cmd_voices(args: argparse.Namespace) -> int:
    """List available neural voices."""
    if not (getattr(args, "json", False) or getattr(args, "agent", False)):
        ui.info("Querying neural speech voices from Microsoft Azure / Edge-TTS...")

    try:
        voices = asyncio.run(query_voices(args.locale, args.gender))
    except Exception as e:
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": str(e)}))
        else:
            render_error_panel("Voice Discovery Failed", str(e))
        return 1

    payload = {
        "status": "ok",
        "total_voices": len(voices),
        "recommended": RECOMMENDED_VOICES,
        "voices": voices[:args.limit],
    }

    if output_structured_data(payload, args) == 0:
        return 0

    lines = [
        f"{ui.bold('Short Name'):<32} {ui.bold('Locale'):<10} {ui.bold('Gender'):<8} {ui.bold('Description')}",
        "─" * 74,
    ]

    for v in voices[:args.limit]:
        lines.append(f"{v['name']:<32} {v['locale']:<10} {v['gender']:<8} {v['friendly'][:22]}")

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
        err = "ffmpeg and ffprobe must be installed and in PATH."
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": err}))
        else:
            render_error_panel("Missing Dependency", err)
        return 1

    transcript_file = Path(args.transcript).resolve()
    if not transcript_file.is_file():
        err = f"Transcript file does not exist: {transcript_file}"
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": err}))
        else:
            render_error_panel("File Not Found", err)
        return 1

    out_dir = Path(args.output_dir).resolve() if args.output_dir else transcript_file.parent

    if not (getattr(args, "json", False) or getattr(args, "agent", False)):
        ui.info(f"Synthesizing transcript: {ui.bold(transcript_file.name)}")
        ui.info(f"Voice: {ui.cyan(args.voice)} | Rate: {args.rate}")

    def progress(msg: str, current: int, total: int) -> None:
        if not (getattr(args, "json", False) or getattr(args, "agent", False)):
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
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": str(e)}))
        else:
            render_error_panel("Synthesis Failed", str(e))
        return 1

    m4b_size_mb = m4b_path.stat().st_size / (1024 * 1024)
    payload = {
        "status": "ok",
        "m4b_file": str(m4b_path),
        "mp3_file": str(mp3_path),
        "size_bytes": m4b_path.stat().st_size,
        "size_mb": round(m4b_size_mb, 2),
    }

    if output_structured_data(payload, args) == 0:
        return 0

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
        err = "ffmpeg and ffprobe must be installed and in PATH."
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": err}))
        else:
            render_error_panel("Missing Dependency", err)
        return 1

    input_paths: list[Path] = []
    discovered_meta: dict[str, Any] = {}

    for item in args.inputs:
        p = Path(item).resolve()
        if p.is_dir() or p.suffix.lower() in (".yaml", ".yml", ".toml"):
            m_meta, ch_files = resolve_ordered_chapters(p, extension=args.ext)
            discovered_meta.update(m_meta)
            input_paths.extend(ch_files)
        elif p.is_file():
            input_paths.append(p)

    if not input_paths:
        err = "No matching audio files found to stitch."
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": err}))
        else:
            render_error_panel("No Chapter Files", err)
        return 1

    final_title = args.title if args.title != "Master Course Companion" else discovered_meta.get("title", args.title)
    final_author = args.author if args.author != "Skald Narrator" else discovered_meta.get("author", args.author)
    final_album = args.album if args.album != "Course Audio Companion" else discovered_meta.get("album", args.album)

    output_m4b = Path(args.output).resolve()
    output_mp3 = output_m4b.with_suffix(".mp3") if args.mp3 else None
    cover_path = Path(args.cover).resolve() if args.cover else None

    if not (getattr(args, "json", False) or getattr(args, "agent", False)):
        ui.info(f"Stitching {len(input_paths)} chapter files into {ui.bold_cyan(output_m4b.name)}...")

    def progress(msg: str, current: int, total: int) -> None:
        if not (getattr(args, "json", False) or getattr(args, "agent", False)):
            pct = (current / total) * 100
            print(f"  {ui.badge()} [{pct:5.1f}%] {msg}", flush=True)

    try:
        m4b_res, mp3_res = stitch_audiobook(
            chapter_files=input_paths,
            output_m4b=output_m4b,
            output_mp3=output_mp3,
            title=final_title,
            author=final_author,
            album=final_album,
            cover_image=cover_path,
            progress_callback=progress,
        )
    except Exception as e:
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": str(e)}))
        else:
            render_error_panel("Stitching Failed", str(e))
        return 1

    m4b_size_mb = m4b_res.stat().st_size / (1024 * 1024)
    payload = {
        "status": "ok",
        "master_m4b": str(m4b_res),
        "master_mp3": str(mp3_res) if mp3_res else None,
        "total_chapters": len(input_paths),
        "size_bytes": m4b_res.stat().st_size,
        "size_mb": round(m4b_size_mb, 2),
    }

    if output_structured_data(payload, args) == 0:
        return 0

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
        err = f"Audiobook file does not exist: {m4b_file}"
        if getattr(args, "json", False) or getattr(args, "agent", False):
            print(json.dumps({"status": "error", "error": err}))
        else:
            render_error_panel("File Not Found", err)
        return 1

    meta = read_audiobook_metadata(m4b_file)
    dur_str = format_duration(meta["duration"])
    size_mb = m4b_file.stat().st_size / (1024 * 1024)

    payload = {
        "status": "ok",
        "file": str(m4b_file),
        "size_bytes": m4b_file.stat().st_size,
        "size_mb": round(size_mb, 2),
        "duration_seconds": meta["duration"],
        "duration_formatted": dur_str,
        "bitrate": meta["bitrate"],
        "metadata": meta,
    }

    if output_structured_data(payload, args) == 0:
        return 0

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


def cmd_mcp(args: argparse.Namespace) -> int:
    """Run JSON-RPC 2.0 stdio MCP server."""
    server = StdioMCPServer()
    server.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    handle_color_args(raw_args)
    handle_agent_args(raw_args)

    if any(a in ("-V", "--version") for a in raw_args):
        print(f"skald {__version__}")
        return 0

    parent_parser = argparse.ArgumentParser(add_help=False)
    add_color_args(parent_parser)
    add_agent_args(parent_parser)
    parent_parser.add_argument("--client", action="store_true", help="Machine client mode (alias for --agent)")

    parser = argparse.ArgumentParser(
        prog="skald",
        description="Arctic oral companion & multi-chapter M4B audiobook compiler.",
        parents=[parent_parser],
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Skald subcommands")

    # narrate
    p_narrate = subparsers.add_parser("narrate", aliases=["recite"], parents=[parent_parser], help="Synthesize a markdown transcript")
    p_narrate.add_argument("transcript", help="Path to markdown transcript file")
    p_narrate.add_argument("--voice", default="en-US-GuyNeural", help="Neural TTS voice (default: en-US-GuyNeural)")
    p_narrate.add_argument("--rate", default="+0%", help="Speech rate adjustment (e.g. +5%%, -10%%)")
    p_narrate.add_argument("--output-dir", "-o", help="Target output directory")

    # stitch
    p_stitch = subparsers.add_parser("stitch", parents=[parent_parser], help="Stitch multiple chapters into master M4B")
    p_stitch.add_argument("inputs", nargs="+", help="Directory or chapter audio files to stitch")
    p_stitch.add_argument("--output", "-o", default="Master_Audiobook.m4b", help="Output M4B filename")
    p_stitch.add_argument("--title", default="Master Course Companion", help="Audiobook title")
    p_stitch.add_argument("--author", default="Skald Narrator", help="Audiobook author")
    p_stitch.add_argument("--album", default="Course Audio Companion", help="Album / series title")
    p_stitch.add_argument("--cover", help="Cover art image (PNG or JPG)")
    p_stitch.add_argument("--ext", default=".m4b", help="File extension to scan when directory given (.m4b or .mp3)")
    p_stitch.add_argument("--mp3", action="store_true", help="Also generate stitched MP3")

    # voices
    p_voices = subparsers.add_parser("voices", parents=[parent_parser], help="Query and list available neural voices")
    p_voices.add_argument("--locale", "-l", help="Filter by locale code (e.g. en-US, nl-NL)")
    p_voices.add_argument("--gender", "-g", help="Filter by gender (Male or Female)")
    p_voices.add_argument("--limit", type=int, default=25, help="Maximum voices to display (default: 25)")

    # inspect
    p_inspect = subparsers.add_parser("inspect", parents=[parent_parser], help="Inspect M4B metadata and chapters")
    p_inspect.add_argument("file", help="Path to M4B audiobook file")

    # mcp
    p_mcp = subparsers.add_parser("mcp", parents=[parent_parser], help="Run Model Context Protocol (MCP) stdio server")

    args = parser.parse_args(argv)

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
    elif args.subcommand == "mcp":
        return cmd_mcp(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
