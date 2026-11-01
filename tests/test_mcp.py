"""Unit tests for Skald MCP server protocol, multi-voice parsing, and text sanitization."""

from __future__ import annotations

import json
from skald.mcp import StdioMCPServer, TOOL_DEFINITIONS, execute_tool
from skald.synthesizer import parse_multivoice_turns, sanitize_speech_text


def test_sanitize_speech_text_advanced() -> None:
    raw = """
    This is a   sentence   with    multiple   spaces.
    
    Here is some **bold text** and *italic text* and [a link](https://example.com).
    $$
    \\min f(x)
    $$
    And $x \\le 0$.
    """
    clean = sanitize_speech_text(raw)
    assert "multiple spaces" in clean
    assert "   " not in clean
    assert "**bold" not in clean
    assert "[a link]" not in clean
    assert "a link" in clean
    assert "\\min" not in clean
    assert "$x" not in clean


def test_parse_multivoice_turns() -> None:
    body = """**Alice:** Welcome to the optimization lab.

**Bob:** Is the problem strictly convex?

**Alice:** Yes, the Hessian is positive definite everywhere."""

    speaker_map = {
        "Alice": "en-US-AriaNeural",
        "Bob": "en-US-GuyNeural",
    }

    turns = parse_multivoice_turns(body, default_voice="en-US-GuyNeural", speaker_map=speaker_map)
    assert len(turns) == 3
    assert turns[0].speaker == "Alice"
    assert turns[0].voice == "en-US-AriaNeural"
    assert "Welcome" in turns[0].text
    assert turns[1].speaker == "Bob"
    assert turns[1].voice == "en-US-GuyNeural"
    assert turns[2].speaker == "Alice"


def test_mcp_initialize() -> None:
    server = StdioMCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-agent", "version": "1.0"},
        },
    }
    resp = server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "skald"


def test_mcp_tools_list() -> None:
    server = StdioMCPServer()
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    resp = server.handle_request(req)
    assert resp is not None
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "skald_narrate" in tool_names
    assert "skald_stitch" in tool_names
    assert "skald_voices" in tool_names
    assert "skald_inspect" in tool_names


def test_mcp_execute_unknown() -> None:
    res = execute_tool("nonexistent_tool", {})
    assert res["status"] == "error"
    assert "Unknown tool" in res["error"]
