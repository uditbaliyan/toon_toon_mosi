"""
subtitle_generator.py
Converts Gentle-aligned word list into a styled .ass subtitle file.
Groups words into phrase-level chunks for natural readability.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger("ToonToon.SubtitleGenerator")


# ---------------------------------------------------------------------------
# ASS header — JarToon style: bold yellow, black outline, centred bottom
# ---------------------------------------------------------------------------
_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,52,&H0000FFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# How many words per subtitle chunk (tune to taste)
_WORDS_PER_CHUNK = 5

# Minimum gap (seconds) between two words to force a new chunk
_SILENCE_SPLIT_THRESHOLD = 0.4


def _to_ass_time(seconds: float) -> str:
    """Convert float seconds → ASS timestamp H:MM:SS.cc"""
    seconds = max(0.0, seconds)
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _chunk_words(aligned_words) -> List[List]:
    """
    Group AlignedWord objects into phrase-level chunks.
    Splits on:
      - every _WORDS_PER_CHUNK words
      - silence gaps > _SILENCE_SPLIT_THRESHOLD seconds
    """
    chunks: List[List] = []
    current: List = []

    for i, word in enumerate(aligned_words):
        # Skip unaligned tokens (Gentle marks these with start/end == None)
        if word.start_time is None or word.end_time is None:
            continue

        # Force split on long silence gap
        if current and (word.start_time - current[-1].end_time) > _SILENCE_SPLIT_THRESHOLD:
            chunks.append(current)
            current = []

        current.append(word)

        # Split on word count
        if len(current) >= _WORDS_PER_CHUNK:
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)

    return chunks


def generate_ass(aligned_words, output_path: str | Path) -> Path:
    """
    Build a .ass subtitle file from Gentle-aligned words.

    Args:
        aligned_words : list of AlignedWord (must have .word, .start_time, .end_time)
        output_path   : destination path for the .ass file

    Returns:
        Path to the written .ass file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chunks = _chunk_words(aligned_words)
    logger.info(f"Subtitle chunking: {len(aligned_words)} words → {len(chunks)} subtitle events")

    lines: List[str] = [_ASS_HEADER]

    for chunk in chunks:
        start = _to_ass_time(chunk[0].start_time)
        end   = _to_ass_time(chunk[-1].end_time)
        text  = " ".join(w.word.upper() for w in chunk)  # uppercase like JarToon

        # ASS Dialogue line
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"ASS subtitle file written → {output_path.resolve()}")
    return output_path