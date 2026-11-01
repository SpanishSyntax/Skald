"""Unit tests for Skald 4-tier document ordering and discovery protocol."""

from __future__ import annotations

from pathlib import Path
from skald.discovery import natural_sort_key, resolve_ordered_chapters


def test_natural_sort_key() -> None:
    files = [Path("ch10.md"), Path("ch1.md"), Path("ch2.md"), Path("ch20.md")]
    sorted_files = sorted(files, key=natural_sort_key)
    names = [f.name for f in sorted_files]
    assert names == ["ch1.md", "ch2.md", "ch10.md", "ch20.md"]


def test_resolve_ordered_chapters_from_yaml(tmp_path: Path) -> None:
    ch1 = tmp_path / "01_intro.md"
    ch2 = tmp_path / "02_theory.md"
    ch1.write_text("# Chapter 1", encoding="utf-8")
    ch2.write_text("# Chapter 2", encoding="utf-8")

    manifest = tmp_path / "audiobook.yaml"
    manifest.write_text("""
title: "Distributed Systems"
author: "Alice"
chapters:
  - 02_theory.md
  - 01_intro.md
""", encoding="utf-8")

    meta, chapters = resolve_ordered_chapters(manifest)
    assert meta["title"] == "Distributed Systems"
    assert meta["author"] == "Alice"
    assert len(chapters) == 2
    # Verify exact custom ordering from manifest, not alphabetical
    assert chapters[0].name == "02_theory.md"
    assert chapters[1].name == "01_intro.md"


def test_resolve_ordered_chapters_fallback_natural(tmp_path: Path) -> None:
    ch10 = tmp_path / "ch10.m4b"
    ch1 = tmp_path / "ch1.m4b"
    ch2 = tmp_path / "ch2.m4b"
    for f in (ch10, ch1, ch2):
        f.touch()

    meta, chapters = resolve_ordered_chapters(tmp_path, extension=".m4b")
    assert len(chapters) == 3
    assert [c.name for c in chapters] == ["ch1.m4b", "ch2.m4b", "ch10.m4b"]
