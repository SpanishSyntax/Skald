"""Neural voice discovery and querying engine for Skald."""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

RECOMMENDED_VOICES = {
    "en-narrator": {
        "short_name": "en-US-GuyNeural",
        "gender": "Male",
        "description": "Warm, articulate narrative voice (Ideal for technical companions)",
    },
    "en-academic": {
        "short_name": "en-US-AriaNeural",
        "gender": "Female",
        "description": "Clear, engaging academic lecture tone",
    },
    "en-deep": {
        "short_name": "en-US-ChristopherNeural",
        "gender": "Male",
        "description": "Deep, authoritative documentary tone",
    },
    "nl-narrator": {
        "short_name": "nl-NL-MaartenNeural",
        "gender": "Male",
        "description": "Natural Dutch academic / technical narrator",
    },
    "nl-academic": {
        "short_name": "nl-NL-FennaNeural",
        "gender": "Female",
        "description": "Clear, expressive Dutch voice",
    },
}


async def query_voices(locale_filter: str | None = None, gender_filter: str | None = None) -> list[dict[str, Any]]:
    """Query available Microsoft Azure Neural voices via edge-tts."""
    try:
        import edge_tts
        voices = await edge_tts.list_voices()
    except Exception:
        # Fallback to recommended list if offline
        voices = [
            {
                "ShortName": v["short_name"],
                "Locale": v["short_name"][:5],
                "Gender": v["gender"],
                "FriendlyName": v["description"],
            }
            for v in RECOMMENDED_VOICES.values()
        ]

    filtered = []
    for v in voices:
        short = v.get("ShortName", "")
        locale = v.get("Locale", "")
        gender = v.get("Gender", "")

        if locale_filter and not locale.lower().startswith(locale_filter.lower()):
            continue
        if gender_filter and gender.lower() != gender_filter.lower():
            continue

        filtered.append({
            "name": short,
            "locale": locale,
            "gender": gender,
            "friendly": v.get("FriendlyName", ""),
        })

    filtered.sort(key=lambda x: (x["locale"], x["name"]))
    return filtered


def get_available_voices(locale: str | None = None, gender: str | None = None) -> list[dict[str, Any]]:
    """Synchronous wrapper for querying voices."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(query_voices(locale, gender))
        else:
            return asyncio.run(query_voices(locale, gender))
    except Exception:
        return asyncio.run(query_voices(locale, gender))
