"""
System constants, phoneme mappings, and animation configuration.

MOUTH SHAPE SLOT TABLE  (11 per sentiment bucket)
─────────────────────────────────────────────────
This table reflects the ACTUAL file order of the mouth PNG assets
(mouth0001..mouth0011 for positive, mouth0012..mouth0022 for negative).
The slot numbers here match what the original render_frames.py used,
which the mouth files were designed for.

Renderer computes the file index as:
  positive: slot + 1           → mouth0001..mouth0011
  negative: slot + 1 + 11      → mouth0012..mouth0022

Slot  Key   File        Description
  0   "y"   mouth0001   Narrow / smile-corners (resting jaw position)
  1   —     mouth0002   y + u rounding tinge  (written only by u-adjacency modifier)
  2   —     mouth0003   Mid-open ramp          (written only by 'a' arc)
  3   —     mouth0004   Mid-open + u rounding  (written only by u-adjacency modifier)
  4   —     mouth0005   Peak-open              (written only by 'a' arc)
  5   —     mouth0006   Peak-open alt          (written only by 'a' arc, long vowels)
  6   "t"   mouth0007   Teeth / tongue near palate
  7   "f"   mouth0008   Upper-teeth on lower-lip
  8   "m"   mouth0009   Lips fully closed (resting, silence)
  9   "o"   mouth0010   Wide-rounded O ring (u-arc edges, er/r/w opening)
 10   "u"   mouth0011   Tight rounded oo sustain

NOTE: Slots 1-5 are intermediate shapes written only by the arc system
internally; they are never referenced by name in MOUTH_SHAPE_CODES.
The 'a' arc maps level values directly to these slot numbers.
The u-adjacency modifier (+1 on adjacent frames) handles slots 1 and 3.

Diphthongs "au", "ay", "ua" are decomposed by the scheduler into their
component arcs and never written directly.
"""

POSE_CHANGE_MIN_SECONDS = 2
POSE_CHANGE_MAX_SECONDS = 6

# ============================================================================
# CANVAS & FRAME CONFIGURATION
# ============================================================================

FRAME_RATE    = 30
CANVAS_WIDTH  = 1280
CANVAS_HEIGHT = 720
COORDINATE_UPSCALE_FACTOR = 3

# ============================================================================
# CHARACTER POSE & EMOTION CONFIGURATION
# ============================================================================

POSE_COUNT    = 5
EMOTION_COUNT = 6
BLINK_STATES  = 3
TOTAL_POSE_VARIATIONS = POSE_COUNT * EMOTION_COUNT * BLINK_STATES  # 90

EMOTIONS = {
    "explain": 0,
    "happy":   1,
    "sad":     2,
    "angry":   3,
    "confused":4,
    "rq":      5,
}

EMOTION_FOLDER = {0:"explain", 1:"happy", 2:"sad", 3:"angry", 4:"confused", 5:"rq"}

# 1 = positive (mouths/happy/), 0 = negative (mouths/sad/)
EMOTION_POSITIVITY = [1, 1, 0, 0, 0, 1]
MOUTH_FOLDER = {1: "happy", 0: "sad"}

EMOTION_POSE_OFFSET = {0:1, 1:16, 2:31, 3:46, 4:61, 5:76}

# ============================================================================
# PHONEME & MOUTH CONFIGURATION
# ============================================================================

MOUTH_COUNT = 22   # 11 positive + 11 negative

PHONEME_MAP = {
    # ── Open vowels → "a" arc ────────────────────────────────────────────
    "aa": "a",   # trap/lot
    "ae": "a",   # trap
    "ah": "a",   # strut / schwa
    "ao": "a",   # thought/cloth  (pure open — NOT a diphthong)
    "eh": "a",   # dress
    "ih": "a",   # kit (short open)

    # ── Diphthongs → two-event split (handled in scheduler) ──────────────
    "aw": "au",  # mouth/out  → a-arc + u-arc
    "ow": "au",  # goat/so    → a-arc + u-arc
    "ay": "ay",  # price/high → a-arc + y-flat
    "ey": "ay",  # face/day
    "iy": "ay",  # fleece     (final narrowing mirrors ay glide)
    "oy": "ua",  # choice     → u-arc + a-arc

    # ── Rounded vowels → "u" arc ─────────────────────────────────────────
    "er": "u",   # nurse/letter
    "uw": "u",   # goose
    "uh": "u",   # foot

    # ── Labials (bilabial closure) ────────────────────────────────────────
    "b":  "m",
    "m":  "m",
    "p":  "m",

    # ── Labio-dentals ─────────────────────────────────────────────────────
    "f":  "f",
    "v":  "f",

    # ── Coronal / dental / velar ──────────────────────────────────────────
    "ch": "t",
    "d":  "t",
    "dh": "t",
    "g":  "t",
    "jh": "t",
    "k":  "t",
    "n":  "t",
    "ng": "t",
    "s":  "t",
    "sh": "t",
    "t":  "t",
    "z":  "t",
    "zh": "t",

    # ── Interdental ───────────────────────────────────────────────────────
    # "th" aliases to "t" because mouth0010 (slot 9) is the O-open shape
    # in the original asset order, not a tongue-between-teeth sprite.
    # If new "th" assets are ever created, update this and MOUTH_SHAPE_CODES.
    "th": "t",

    # ── Approximants / glides ─────────────────────────────────────────────
    "hh": "y",
    "l":  "y",
    "r":  "u",   # rhotic approximant — rounded
    "w":  "u",   # labio-velar approximant — rounded
    "y":  "y",

    # ── Silence / OOV ─────────────────────────────────────────────────────
    "sil": "m",
    "oov": "m",
}

# Slot index for each abstract shape (0-based within sentiment bucket).
# These numbers MUST match the actual mouth PNG file order on disk.
# File index = slot + 1  (positive)  or  slot + 1 + 11  (negative).
#
# Slots 1-5 are intermediate arc positions; they are not named here
# because they are never referenced by name — only by numeric offset
# inside the arc system.
MOUTH_SHAPE_CODES = {
    "y":  0,   # narrow / smile           → mouth0001
    # 1                                   → mouth0002  (y + u tinge, arc only)
    # 2                                   → mouth0003  (mid-open, arc only)
    # 3                                   → mouth0004  (mid + u tinge, arc only)
    # 4                                   → mouth0005  (peak-open, arc only)
    # 5                                   → mouth0006  (peak-open alt, arc only)
    "t":  6,   # teeth / tongue           → mouth0007
    "f":  7,   # teeth on lower lip       → mouth0008
    "m":  8,   # lips closed (resting)    → mouth0009
    "o":  9,   # wide O-ring (u edges)    → mouth0010
    "u":  10,  # tight rounded (oo sust.) → mouth0011
}

POSITIVE_MOUTH_BASE  = 1
NEGATIVE_MOUTH_BASE  = 12
MOUTHS_PER_SENTIMENT = 11

# ============================================================================
# ARC CONFIGURATION
# ============================================================================

# Shapes that leave the lips/jaw slightly open, so the adjacent 'a' arc
# starts or ends at "y" (narrow) rather than "m" (closed).
# Matches the original START_FORCE_OPEN / END_FORCE_OPEN condition:
#   prev/next in ('t', 'y')
# 'f' added because it also leaves the jaw open.
OPEN_VOWEL_FORCE_OPEN_SHAPES = {"t", "y", "f"}

# ============================================================================
# PHONEME ANIMATION LOGIC (legacy constants, kept for compatibility)
# ============================================================================

MAX_JIGGLE_TIME      = 2
JIGGLE_FADER         = 0.06
JIGGLE_MULTIPLIER    = 0.6
SENTENCE_TERMINATORS = {",", ";", ".", ":", "!", "?"}

# ============================================================================
# RENDERING CONFIGURATION
# ============================================================================

BODY_SCALE_POSITION_X = 0.75
BODY_BASE_HEIGHT      = 1.0
MARGIN                = 20
FRAME_CACHE_ENABLED   = True
PRINT_PROGRESS_EVERY  = 10

# ============================================================================
# AUDIO CONFIGURATION
# ============================================================================

BACKGROUND_MUSIC_VOLUME = 0.044