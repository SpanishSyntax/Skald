"""Model Context Protocol (MCP) server for Skald."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from skald import __version__
from skald.metadata import read_audiobook_metadata
from skald.muxer import check_ffmpeg
from skald.stitcher import discover_chapter_files, stitch_audiobook
from skald.synthesizer import synthesize_transcript
from skald.voices import query_voices

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "skald_narrate",
        "description": "Synthesizes a markdown lecture transcript into an M4B audiobook and MP3 audio with embedded QuickTime chapter markers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "transcript_path": {
                    "type": "string",
                    "description": "Path to the markdown transcript file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional destination directory for the generated audio files.",
                },
                "voice": {
                    "type": "string",
                    "description": "Neural TTS voice (default: en-US-GuyNeural).",
                },
                "rate": {
                    "type": "string",
                    "description": "Speech rate adjustment (e.g. +0%, +5%, -10%).",
                },
            },
            "required": ["transcript_path"],
        },
    },
    {
        "name": "skald_stitch",
        "description": "Stitches multiple chapter audio files into a unified master M4B audiobook with millisecond chapter markers and metadata tags.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chapter_dir": {
                    "type": "string",
                    "description": "Directory or manifest file (audiobook.yaml, book.toml) declaring chapters (default: current directory).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Destination path for the compiled master M4B file.",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the master audiobook.",
                },
                "author": {
                    "type": "string",
                    "description": "Author or narrator name.",
                },
                "album": {
                    "type": "string",
                    "description": "Series or course title.",
                },
                "include_mp3": {
                    "type": "boolean",
                    "description": "Whether to also export a unified MP3 file (default: true).",
                },
            },
            "required": ["chapter_dir", "output_path"],
        },
    },
    {
        "name": "skald_voices",
        "description": "Queries and lists available Microsoft Azure / Edge-TTS neural voices filterable by locale and gender.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locale": {
                    "type": "string",
                    "description": "Optional locale code filter (e.g. en-US, nl-NL, de-DE).",
                },
                "gender": {
                    "type": "string",
                    "description": "Optional gender filter (Male or Female).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of voices to return (default: 30).",
                },
            },
        },
    },
    {
        "name": "skald_inspect",
        "description": "Inspects duration, bitrate, chapters, and metadata tags of an M4B audiobook file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audio_path": {
                    "type": "string",
                    "description": "Path to the M4B audiobook file to inspect.",
                },
            },
            "required": ["audio_path"],
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a Skald MCP tool call and return JSON-serializable results."""
    try:
        if name == "skald_narrate":
            if not check_ffmpeg():
                return {"status": "error", "error": "ffmpeg and ffprobe must be installed in PATH."}

            t_path = Path(arguments["transcript_path"]).resolve()
            if not t_path.is_file():
                return {"status": "error", "error": f"Transcript not found: {t_path}"}

            out_dir = Path(arguments.get("output_dir", t_path.parent)).resolve()
            voice = arguments.get("voice", "en-US-GuyNeural")
            rate = arguments.get("rate", "+0%")

            m4b_path, mp3_path = asyncio.run(
                synthesize_transcript(
                    transcript_path=t_path,
                    output_dir=out_dir,
                    voice=voice,
                    rate=rate,
                )
            )

            return {
                "status": "ok",
                "m4b_file": str(m4b_path),
                "mp3_file": str(mp3_path),
                "m4b_size_bytes": m4b_path.stat().st_size,
            }

        elif name == "skald_stitch":
            if not check_ffmpeg():
                return {"status": "error", "error": "ffmpeg and ffprobe must be installed in PATH."}

            target = Path(arguments.get("chapter_dir", arguments.get("manifest_path", "."))).resolve()
            if not target.exists():
                return {"status": "error", "error": f"Target path not found: {target}"}

            from skald.discovery import resolve_ordered_chapters
            m_meta, files = resolve_ordered_chapters(target, extension=".m4b")
            if not files:
                m_meta, files = resolve_ordered_chapters(target, extension=".mp3")
            if not files:
                return {"status": "error", "error": f"No chapter audio files found for {target}"}

            out_m4b = Path(arguments["output_path"]).resolve()
            include_mp3 = arguments.get("include_mp3", True)
            out_mp3 = out_m4b.with_suffix(".mp3") if include_mp3 else None

            title = arguments.get("title") or m_meta.get("title", "Audiobook Companion")
            author = arguments.get("author") or m_meta.get("author", "Skald Narrator")
            album = arguments.get("album") or m_meta.get("album", "Audiobook Series")

            m4b_res, mp3_res = stitch_audiobook(
                chapter_files=files,
                output_m4b=out_m4b,
                output_mp3=out_mp3,
                title=title,
                author=author,
                album=album,
            )

            return {
                "status": "ok",
                "master_m4b": str(m4b_res),
                "master_mp3": str(mp3_res) if mp3_res else None,
                "chapters_stitched": len(files),
                "size_bytes": m4b_res.stat().st_size,
            }

        elif name == "skald_voices":
            locale = arguments.get("locale")
            gender = arguments.get("gender")
            limit = arguments.get("limit", 30)

            voices = asyncio.run(query_voices(locale_filter=locale, gender_filter=gender))
            return {
                "status": "ok",
                "total_found": len(voices),
                "voices": voices[:limit],
            }

        elif name == "skald_inspect":
            a_path = Path(arguments["audio_path"]).resolve()
            if not a_path.is_file():
                return {"status": "error", "error": f"Audio file not found: {a_path}"}

            info = read_audiobook_metadata(a_path)
            return {
                "status": "ok",
                "file": str(a_path),
                "size_bytes": a_path.stat().st_size,
                "metadata": info,
            }

        else:
            return {"status": "error", "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"status": "error", "error": str(e)}


class StdioMCPServer:
    """JSON-RPC 2.0 stdio server implementing the Model Context Protocol."""

    def __init__(self) -> None:
        self.server_info = {"name": "skald", "version": __version__}

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        method = req.get("method")
        msg_id = req.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": self.server_info,
                    "capabilities": {"tools": {}},
                },
            }

        elif method == "notifications/initialized":
            return None

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOL_DEFINITIONS},
            }

        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments", {})
            res = execute_tool(name, args)
            is_error = res.get("status") == "error"

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                    "isError": is_error,
                },
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    def run(self) -> None:
        """Run JSON-RPC event loop reading lines from sys.stdin."""
        for line in sys.stdin:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                req = json.loads(line_str)
                resp = self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
