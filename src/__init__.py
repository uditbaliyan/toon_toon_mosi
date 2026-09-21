"""
ToonToon: High-Performance Unified Animation Pipeline

A complete refactoring of Cary's lazykh legacy animation system into a single,
production-ready Python engine that streams frames directly to FFmpeg without
intermediate disk I/O.

Exported Subsystems:
    - Models: Immutable frozen dataclasses representing pipeline state.
    - Parser: Text tokenizer matching brackets and sentence boundaries.
    - Aligner: HTTP post client interacting with forced aligner.
    - Scheduler: Dynamic vowel mapping scheduler aligning time tracks.
    - Renderer: Compositing engine applying region translations and blending.
    - Compositor: FFmpeg subprocess writer using raw frame stdin streams.
"""

from .models import (
    Position2D,
    PoseTransform,
    PhonemeInterval,
    AlignedWord,
    AnimationFrameState,
    CharacterManifest,
)
from .parser import ScriptParser, ScriptMetadata, EmotionEvent
from .aligner import GentleAligner
from .scheduler import AnimationScheduler
from .renderer import FrameRenderer
from .compositor import FFmpegCompositor

__version__ = "1.0.0"
__all__ = [
    "Position2D",
    "PoseTransform",
    "PhonemeInterval",
    "AlignedWord",
    "AnimationFrameState",
    "CharacterManifest",
    "ScriptParser",
    "ScriptMetadata",
    "EmotionEvent",
    "GentleAligner",
    "AnimationScheduler",
    "FrameRenderer",
    "FFmpegCompositor",
]
