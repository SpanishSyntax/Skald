# Configuration & API Reference

This reference covers the YAML frontmatter schema, the Python programmatic library, and QuickTime container tag standards.

---

## Frontmatter Specification

Markdown documents consumed by `skald narrate` can define metadata in a leading YAML block:

```markdown
---
title: "Kalman Filtering and Sensor Fusion"
author: "Alex Rivera"
album: "Optimal State Estimation"
voice: "en-US-AndrewNeural"
rate: "+3%"
volume: "+0%"
pitch: "+0Hz"
track: 1
year: 2026
---
```

### Schema Properties

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `title` | `string` | Document stem | Title of the chapter or lecture |
| `author` | `string` | `""` | Author or speaker name |
| `album` | `string` | `title` | Master audiobook or course collection title |
| `voice` | `string` | `en-US-AndrewNeural` | Neural voice identifier |
| `rate` | `string` | `"+0%"` | Relative speech velocity (`+10%`, `-5%`) |
| `volume` | `string` | `"+0%"` | Relative volume adjustment |
| `pitch` | `string` | `"+0Hz"` | Relative pitch adjustment |
| `track` | `int` | `1` | Sequential track number |
| `year` | `int` | Current Year | Publication year |

---

## Nix and Home Manager

### Flake Configuration

```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    skald.url = "github:SpanishSyntax/Skald";
    skald.inputs.nixpkgs.follows = "nixpkgs";
  };
}
```

### Home Manager Module

```nix
{
  programs.skald = {
    enable = true;
  };
}
```

---

## Python API Reference

Downstream scripts and automation pipelines can interface with Skald directly in Python:

```python
import pathlib
from skald.synthesizer import synthesize_transcript
from skald.stitcher import stitch_audiobook
from skald.voices import query_voices
from skald.metadata import read_audiobook_metadata
```

### `synthesize_transcript`

Asynchronously converts a Markdown transcript file into audio.

```python
async def synthesize_transcript(
    transcript_path: pathlib.Path,
    output_dir: pathlib.Path,
    voice: str = "en-US-AndrewNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    cover_image: pathlib.Path | None = None,
    generate_mp3: bool = True,
) -> pathlib.Path:
    """Parses transcript, synthesizes chunks, and produces an M4B file.
    
    Returns:
        pathlib.Path: Path to the generated .m4b audiobook.
    """
```

### `stitch_audiobook`

Combines multiple chapter audio files into a single master container.

```python
def stitch_audiobook(
    chapter_files: list[pathlib.Path],
    output_path: pathlib.Path,
    title: str,
    author: str,
    album: str,
    cover_image: pathlib.Path | None = None,
    generate_mp3: bool = False,
) -> pathlib.Path:
    """Concatenates audio files and generates synchronized chapter tracks.
    
    Returns:
        pathlib.Path: Path to the merged .m4b audiobook.
    """
```

### `query_voices`

Asynchronously retrieves available neural voice models.

```python
async def query_voices(
    locale: str | None = None,
    gender: str | None = None,
) -> list[dict[str, str]]:
    """Queries Microsoft Edge-TTS voice registry.
    
    Returns:
        list[dict]: Dictionaries containing name, friendly name, gender, and locale.
    """
```

### `read_audiobook_metadata`

Inspects an audio container file.

```python
def read_audiobook_metadata(path: pathlib.Path) -> dict[str, any]:
    """Reads container duration, bitrates, audio tags, and embedded chapters.
    
    Returns:
        dict: Detailed container telemetry and chapter offsets.
    """
```

---

## QuickTime Tag Standards

Skald embeds standards-compliant iTunes/QuickTime metadata atoms into `.m4b` files via `mutagen.mp4`:

| Atom | MP4 Field | Description |
| :--- | :--- | :--- |
| `©nam` | `title` | Track title |
| `©ART` | `artist` | Author / speaker |
| `©alb` | `album` | Companion collection title |
| `©day` | `date` | Year of publication |
| `trkn` | `track` | Track index and total count tuple |
| `covr` | `cover` | PNG or JPEG binary artwork stream |
| `stbl` | `chapters` | MPEG-4 text track synchronized with audio samples |
