"""Document discovery, manifest resolution, and chapter ordering for Skald."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from skald.metadata import parse_markdown_transcript


def natural_sort_key(s: Path | str) -> list[int | str]:
    """Sort filenames with numbers naturally (e.g. ch1, ch2, ch10)."""
    text = s.name if isinstance(s, Path) else s
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]


def _parse_simple_yaml_manifest(text: str) -> dict[str, Any]:
    """Lightweight zero-dependency YAML parser for book/audiobook manifests."""
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip().lower()
            val = val.strip().strip("\"'")

            if not val:
                # Sub-block: list or dict
                sub_items: list[Any] = []
                i += 1
                while i < len(lines):
                    sub_line = lines[i]
                    sub_stripped = sub_line.strip()
                    if not sub_stripped or sub_stripped.startswith("#"):
                        i += 1
                        continue
                    indent = len(sub_line) - len(sub_line.lstrip(" "))
                    if indent == 0 and not sub_stripped.startswith("-"):
                        break

                    if sub_stripped.startswith("- "):
                        item_content = sub_stripped[2:].strip().strip("\"'")
                        if ":" in item_content:
                            # Dict entry in list, e.g. - path: ch01.md
                            d_key, d_val = item_content.split(":", 1)
                            sub_items.append({d_key.strip(): d_val.strip().strip("\"'")})
                        else:
                            sub_items.append(item_content)
                    i += 1
                result[key] = sub_items
                continue
            else:
                result[key] = val
        i += 1
    return result


def load_manifest_file(manifest_path: Path) -> dict[str, Any]:
    """Load configuration and chapter ordering from a YAML or TOML manifest."""
    content = manifest_path.read_text(encoding="utf-8")
    if manifest_path.suffix.lower() == ".toml":
        try:
            return tomllib.loads(content)
        except Exception:
            return {}
    return _parse_simple_yaml_manifest(content)


def resolve_ordered_chapters(
    target: Path,
    extension: str = ".md",
) -> tuple[dict[str, Any], list[Path]]:
    """
    Resolves an ordered sequence of chapter files and document metadata using a 4-tier strategy:
    1. Explicit Manifest: checks for audiobook.yaml, audiobook.toml, book.yaml, book.toml, skald.yaml.
    2. Master Document Frontmatter: checks index.md, report.md, or master.md for 'chapters' list.
    3. Order File: checks for order.txt or _order.txt.
    4. Natural Alphanumeric Sort: globs files and sorts numerically (ch1, ch2, ch10).
    """
    meta: dict[str, Any] = {}
    ordered_files: list[Path] = []

    # If target is explicitly a manifest file
    if target.is_file() and target.suffix.lower() in (".yaml", ".yml", ".toml"):
        data = load_manifest_file(target)
        meta = {k: v for k, v in data.items() if k not in ("chapters", "pages")}
        base_dir = target.parent
        raw_chaps = data.get("chapters", data.get("pages", []))
        for item in raw_chaps:
            rel_p = item if isinstance(item, str) else item.get("path", "")
            if rel_p:
                p = (base_dir / rel_p).resolve()
                if p.exists():
                    ordered_files.append(p)
        return meta, ordered_files

    base_dir = target if target.is_dir() else target.parent

    # Tier 1: Look for manifest in directory
    manifest_candidates = (
        "audiobook.yaml",
        "audiobook.yml",
        "audiobook.toml",
        "book.yaml",
        "book.yml",
        "book.toml",
        "skald.yaml",
        "skald.toml",
        "manifest.yaml",
    )
    for m_name in manifest_candidates:
        m_path = base_dir / m_name
        if m_path.is_file():
            data = load_manifest_file(m_path)
            meta = {k: v for k, v in data.items() if k not in ("chapters", "pages")}
            raw_chaps = data.get("chapters", data.get("pages", []))
            for item in raw_chaps:
                rel_p = item if isinstance(item, str) else item.get("path", "")
                if rel_p:
                    p = (base_dir / rel_p).resolve()
                    if p.exists():
                        ordered_files.append(p)
            if ordered_files:
                return meta, ordered_files

    # Tier 2: Check master frontmatter in index.md, master.md, report.md
    for doc_name in ("index.md", "master.md", "report.md", "book.md"):
        doc_path = base_dir / doc_name
        if doc_path.is_file():
            parsed_meta, _ = parse_markdown_transcript(doc_path.read_text(encoding="utf-8"))
            if "chapters" in parsed_meta:
                raw = parsed_meta["chapters"]
                # Comma or newline separated
                ch_list = [c.strip() for c in re.split(r"[,;\n]", raw) if c.strip()]
                for c_name in ch_list:
                    p = (base_dir / c_name).resolve()
                    if p.exists():
                        ordered_files.append(p)
                if ordered_files:
                    return parsed_meta, ordered_files

    # Tier 3: Check order.txt or _order.txt
    for ord_name in ("order.txt", "_order.txt", "chapters.txt"):
        ord_path = base_dir / ord_name
        if ord_path.is_file():
            lines = [ln.strip() for ln in ord_path.read_text(encoding="utf-8").splitlines()]
            for ln in lines:
                if ln and not ln.startswith("#"):
                    p = (base_dir / ln).resolve()
                    if p.exists():
                        ordered_files.append(p)
            if ordered_files:
                return meta, ordered_files

    # Tier 4: Zero-config fallback to natural sorting
    # Ignore master output files or temp/hidden files
    matched = [
        f for f in base_dir.glob(f"*{extension}")
        if not f.name.lower().startswith(("master", ".", "_"))
    ]
    matched.sort(key=natural_sort_key)
    return meta, matched
