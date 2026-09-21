"""
Defines immutable, type-safe data containers for the animation pipeline.
Ensures clean validation boundaries when parsing timelines between layers.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict


@dataclass(frozen=True)
class Position2D:
    """Represents a 2D coordinate point."""
    x: float
    y: float


@dataclass(frozen=True)
class PoseTransform:
    """Mouth position transformation parameters for a specific pose."""
    anchor: Position2D
    scale_x: float
    scale_y: float
    rotation: float


@dataclass(frozen=True)
class PhonemeInterval:
    """A single phoneme with its acoustic duration."""
    phone: str
    duration: float


@dataclass(frozen=True)
class AlignedWord:
    """A word with its timing and phonetic breakdown from Gentle API."""
    word: str
    start_time: float
    end_time: float
    phones: List[PhonemeInterval] = field(default_factory=list)


@dataclass(frozen=True)
class AnimationFrameState:
    """Complete state vector for a single animation frame."""
    frame_index: int
    paragraph_index: int
    emotion_id: int
    pose_id: int
    phoneme_id: int
    is_flipped: bool
    time_since_pose_change: int
    time_until_pose_change: int


@dataclass(frozen=True)
class CharacterManifest:
    """Character asset configuration metadata."""
    name: str
    pose_count: int
    emotion_count: int
    mouth_count: int
    canvas_width: int
    canvas_height: int
    assets_path: str
