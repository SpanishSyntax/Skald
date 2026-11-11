# CLI & Recipes

Skald provides subcommands for narrating single transcripts, stitching multi-chapter master audiobooks, querying neural voices, and inspecting media files.

---

## Command Reference

The primary binary is `skald`:

```text
usage: skald [-h] [-V] [--color {auto,always,never}] [--no-color] {narrate,recite,stitch,voices,inspect,mcp} ...

Arctic oral companion & multi-chapter M4B audiobook compiler.

subcommands:
  narrate (recite)   Synthesize a markdown transcript into M4B & MP3
  stitch             Stitch multiple chapters into a master M4B audiobook
  voices             Query and list available neural voices
  inspect            Inspect M4B metadata, bitrates, and chapter offsets
  mcp                Run Model Context Protocol stdio server

general options:
  -h, --help         Show help message and exit
  -V, --version      Show version information and exit
  --color MODE       Color output mode: auto, always, never (default: auto)
  --no-color         Disable colored output
  -A, --agent        Machine/agent-friendly output mode
  --json             Output structured JSON payloads
```

---

## Narrate Single Chapters

The `narrate` (or `recite`) command converts a single Markdown transcript into chapter-marked audio files:

```bash
skald narrate transcript.md [options]
```

### Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-o, --output PATH` | Output directory or filename | `./dist` |
| `--voice VOICE` | Edge-TTS voice model name | `en-US-AndrewNeural` |
| `--rate RATE` | Speech rate adjustment (`+5%`, `-10%`) | `+0%` |
| `--volume VOL` | Volume adjustment (`+0%`, `+10%`) | `+0%` |
| `--pitch PITCH` | Pitch adjustment (`+0Hz`, `+5Hz`) | `+0Hz` |
| `--cover PATH` | Path to cover image (`.png` or `.jpg`) | `assets/cover.png` if present |
| `--no-mp3` | Skip generating companion MP3 file | `False` |

### Example

```bash
skald narrate ch01_linear_systems.md \
  --voice en-US-BrianNeural \
  --rate "+4%" \
  --cover assets/cover.png \
  -o audio/
```

---

## Stitch Master Audiobooks

The `stitch` command aggregates multiple chapter audio files or directories into a cohesive master companion:

```bash
skald stitch <input_dir_or_files...> [options]
```

### Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-o, --output PATH` | Output master `.m4b` file path | `./Master_Audiobook.m4b` |
| `--title TITLE` | Master audiobook album/book title | Directory name |
| `--author AUTHOR` | Author / speaker name | None |
| `--album ALBUM` | Album name | Title |
| `--cover PATH` | Cover artwork image file | None |
| `--mp3` | Also generate full-length master MP3 | `False` |

### Example

```bash
skald stitch audio/chapters/ \
  --output audio/Control_Theory_Master.m4b \
  --title "Modern Control Theory" \
  --author "Prof. Alex Rivera" \
  --album "Technical Companions Series" \
  --cover assets/cover.png \
  --mp3
```

---

## Voice Query and Filtering

List and inspect available Microsoft Edge-TTS neural speech models:

```bash
# Display top recommended voices
skald voices

# Filter by BCP 47 locale
skald voices --locale en-US

# Filter by gender and limit output rows
skald voices --locale en-US --gender Female --limit 10

# Emit structured JSON for scripting
skald voices --locale de-DE --json
```

---

## Inspect Metadata

Verify chapter offsets, audio streams, bitrates, and QuickTime atom tags without opening an external GUI:

```bash
skald inspect audio/Control_Theory_Master.m4b
```

Sample output:

```text
╭── Audiobook Inspector ──────────────────────────────────────────────╮
│ Title:       Modern Control Theory                                  │
│ Author:      Prof. Alex Rivera                                      │
│ Album:       Technical Companions Series                            │
│ Duration:    01:42:15                                               │
│ Format:      QuickTime / MOV / M4B (AAC-LC 64 kbps, 24000 Hz)       │
│ Chapters:    8 chapters defined                                     │
│                                                                     │
│  #  Start     End       Title                                       │
│ ─────────────────────────────────────────────────────────────────── │
│  1  00:00:00  00:12:45  Chapter 1: State Space Formulations        │
│  2  00:12:45  00:26:10  Chapter 2: Controllability & Observability  │
│  3  00:26:10  00:41:00  Chapter 3: Lyapunov Stability               │
╰─────────────────────────────────────────────────────────────────────╯
```

---

## Model Context Protocol (MCP)

Skald includes an MCP stdio server allowing autonomous agents to query voices, inspect audio files, and synthesize lecture audio:

```bash
skald mcp
```

Exposed MCP tools:
- `narrate_transcript`: Converts markdown transcript into M4B.
- `stitch_chapters`: Aggregates audio files into master audiobook.
- `list_voices`: Queries supported neural voice models.
- `inspect_audiobook`: Reads media streams and chapter structures.
