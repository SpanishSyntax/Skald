"""Unit tests for Skald metadata parsing, sentence chunking, and FFmetadata generation."""

from __future__ import annotations

from skald.metadata import (
    ChapterInfo,
    build_ffmetadata,
    parse_markdown_transcript,
)
from skald.synthesizer import chunk_text, sanitize_speech_text


def test_sanitize_speech_text() -> None:
    raw = "Let $x \\in \\mathbb{R}^n$ be the state, and `optimize()` the function."
    clean = sanitize_speech_text(raw)
    assert "$x" not in clean
    assert "`" not in clean
    assert "optimize()" in clean


def test_chunk_text() -> None:
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    chunks = chunk_text(text, max_chars=35)
    assert len(chunks) >= 2
    assert "First sentence." in chunks[0]


def test_parse_markdown_transcript() -> None:
    sample_md = """---
title: "Foundations of Optimization"
author: "Antigravity Skald"
album: "Mathematical Foundations"
---

# 1. Introduction to the Problem

Optimization is the science of decision making under constraints.

## 1.1 Feasible Sets and Extreme Points

Points on the boundary define basic feasible solutions.
"""
    meta, sections = parse_markdown_transcript(sample_md)
    assert meta["title"] == "Foundations of Optimization"
    assert meta["author"] == "Antigravity Skald"
    assert len(sections) == 2
    assert "Feasible Sets" in sections[1].title


def test_build_ffmetadata() -> None:
    chaps = [
        ChapterInfo(
            number=1, title="Chapter 01: Foundations", start_ms=0, end_ms=50000
        ),
        ChapterInfo(
            number=2, title="Chapter 02: Simplex", start_ms=50000, end_ms=120000
        ),
    ]
    meta_str = build_ffmetadata(chaps, title="Master Course", author="Narrator")
    assert ";FFMETADATA1" in meta_str
    assert "title=Master Course" in meta_str
    assert "[CHAPTER]" in meta_str
    assert "START=0" in meta_str
    assert "END=50000" in meta_str
    assert "title=Chapter 01: Foundations" in meta_str
