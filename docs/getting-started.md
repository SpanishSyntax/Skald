# Getting Started

Skald turns markdown transcripts into chapter-indexed M4B audiobooks using neural TTS and FFmpeg muxing.

---

## Installation

### Nix Flake (Recommended)

Skald is natively packaged as a Nix Flake bundling Python 3.12, `edge-tts`, `mutagen`, and `ffmpeg` into its hermetic closure:

```bash
# Run directly without installation
nix run github:SpanishSyntax/Skald -- voices

# Enter an interactive dev shell
nix shell github:SpanishSyntax/Skald
```

To add Skald to your NixOS or Home Manager configuration:

```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    skald = {
      url = "github:SpanishSyntax/Skald";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, skald, ... }: {
    homeConfigurations."usurper" = home-manager.lib.homeManagerConfiguration {
      modules = [
        skald.homeManagerModules.default
        {
          programs.skald.enable = true;
        }
      ];
    };
  };
}
```

### Python Package (pip / uv)

Skald can also be installed via Python packaging tools:

```bash
# Install with uv
uv tool install git+https://github.com/SpanishSyntax/Skald.git

# Install with pip
pip install git+https://github.com/SpanishSyntax/Skald.git
```

---

## Prerequisites and Dependencies

When running outside Nix, ensure that `ffmpeg` and `ffprobe` are installed on your host system:

| Dependency | Required Version | Purpose |
| :--- | :--- | :--- |
| `ffmpeg` | `>= 5.0` | Audio stream encoding, AAC/MP3 transcoding, metadata muxing |
| `ffprobe` | `>= 5.0` | Media duration inspection and stream verification |
| Python | `>= 3.10` | Runtime environment for async TTS chunking |

Verify your FFmpeg installation:

```bash
ffmpeg -version
```

---

## Quick Start

### 1. Create a Transcript

Write a markdown file with optional frontmatter and headings. Headings (`#`, `##`) serve as natural chapter markers in the final audiobook:

```markdown
---
title: "Distributed Consensus Foundations"
author: "Alex Rivera"
album: "Autonomous Systems Companion"
---

# Introduction to Consensus

Welcome to this lecture companion on distributed agreement protocols. In this chapter, we explore how independent computing nodes reach agreement in the presence of unreliable networks.

## Synchronous vs Asynchronous Networks

In synchronous systems, communication delay is strictly bounded. However, real-world distributed networks are inherently asynchronous or partially synchronous.
```

### 2. Synthesize to Audiobook

Synthesize the markdown transcript into an M4B audiobook:

```bash
skald narrate transcript.md -o dist/
```

This compiles `dist/transcript.m4b` containing AAC audio, embedded cover metadata, and chapter boundaries mapped to your Markdown headers.

---

## Voice Selection

Skald defaults to high-clarity neural speech voices. You can inspect all available voices and test different accents or languages:

```bash
# Query recommended voices
skald voices

# Filter by locale
skald voices --locale en-US --gender Male

# Narrate using an explicit voice model and adjusted speech rate
skald narrate transcript.md --voice en-US-GuyNeural --rate "+5%"
```
