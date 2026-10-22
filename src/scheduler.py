""""
Animation Scheduler  (v6 — slot-order fix)

ROOT CAUSE FIXED IN v6
──────────────────────────────────────────────────────────────────────────────
The original mouth PNG files (mouth0001..mouth0011) were designed for the
slot numbering used by the original render_frames.py setPhoneme():

    slot 0  = y / narrow-smile        (mouth0001)
    slot 2  = mid-open ramp           (mouth0003)
    slot 4  = peak-open               (mouth0005)
    slot 5  = peak-open alt           (mouth0006)
    slot 6  = t / teeth               (mouth0007)
    slot 7  = f / lip-teeth           (mouth0008)
    slot 8  = m / closed              (mouth0009)
    slot 9  = o / O-open (u edges)    (mouth0010)
    slot 10 = u / tight-round sustain (mouth0011)

v3–v5 introduced a new MOUTH_SHAPE_CODES that shuffled these numbers
(m→4, t→5, o→6, u→2, y→1, …) WITHOUT renaming the PNG files, causing every
shape to load the wrong sprite.  That is fixed in config.py v6.

ADDITIONAL ARC BUGS FIXED IN v6
──────────────────────────────────────────────────────────────────────────────

BUG A — _LEVEL_TO_SLOT was backwards
  v3-v5: {0:4, 2:1, 4:0, 5:0}  → level 0 (resting narrow) mapped to slot 4
          (peak-open!), and level 4 (open peak) mapped to slot 0 (narrow).
          The arc was visually inverted: the character opened its mouth where
          it should close and closed it where it should open.
  Fix:   {0:0, 2:2, 4:4, 5:5}  → identity mapping (levels ARE slot numbers
          in the original system).

BUG B — u-adjacency +1 modifier was removed
  v3–v5 dropped the +1 modifier that bumps the first/last frame of an 'a'
  arc when adjacent to a 'u' phoneme.  This modifier blends the lip-rounding
  of 'u' into the edge of the 'a' arc, producing natural a→u and u→a
  coarticulation.  Without it the transition is abrupt and 'u' sequences
  look jerky.
  Fix:   Re-added to _a_arc().  The modifier bumps slot n → n+1 on the
          boundary frame (e.g. narrow slot 0 → slot 1 which is the y+u blend,
          mid-open slot 2 → slot 3 which is the mid+u blend).

BUG C — _u_arc used wrong slot references
  v3–v5: referenced MOUTH_SHAPE_CODES["o"] and ["u"] which under the broken
          slot scheme returned 6 and 2 respectively, landing on wrong files.
  Fix:   Now references the corrected MOUTH_SHAPE_CODES (9 and 10) which
          correctly point to mouth0010 (O-open) and mouth0011 (tight-round).

BUG D — "th" mapped to slot 9 → mouth0010 = O-open in original files
  v5 gave "th" its own slot (9) but mouth0010 is the O-open shape, not a
  tongue-between-teeth sprite.  Result: "th" sounds showed an O-mouth.
  Fix:   PHONEME_MAP maps "th" → "t" (slot 6 = mouth0007 = teeth/tongue).
          This matches the original schedule_maker.py behaviour.

BUGS FIXED IN v5 (unchanged here)
──────────────────────────────────────────────────────────────────────────────
• Universal -2 anticipation offset on every phoneme event.
• Shape-identity deduplication (no gap insertion between same-shape events).
• Line-break-only mouth closing (not after every word).
"""

import logging
import math
import random

import numpy as np

from .config import (
    FRAME_RATE,
    POSE_COUNT,
    PHONEME_MAP,
    MOUTH_SHAPE_CODES,
    POSE_CHANGE_MIN_SECONDS,
    POSE_CHANGE_MAX_SECONDS,
    EMOTIONS,
    OPEN_VOWEL_FORCE_OPEN_SHAPES,
)

logger = logging.getLogger("ToonToon.Scheduler")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FORCE_OPEN_SET = OPEN_VOWEL_FORCE_OPEN_SHAPES   # {"t", "y", "f"}

# Shapes that the ORIGINAL treated as "open" for line-break mouth closing.
_OPEN_SHAPES_FOR_CLOSE = {"a", "f", "u", "y"}

_SENTENCE_STOPPERS = {",", ";", ".", ":", "!", "?"}

# ---------------------------------------------------------------------------
# Emotion name → ID
# ---------------------------------------------------------------------------

_EMOTION_NAME_MAP: dict = {}


def _build_emotion_name_map() -> dict:
    if isinstance(EMOTIONS, dict):
        return {k.lower(): v for k, v in EMOTIONS.items()}
    return {name.lower(): idx for idx, name in enumerate(EMOTIONS)}


def _emotion_name_to_id(name: str) -> int:
    global _EMOTION_NAME_MAP
    if not _EMOTION_NAME_MAP:
        _EMOTION_NAME_MAP = _build_emotion_name_map()
    key = name.lower().strip()
    if key in _EMOTION_NAME_MAP:
        return _EMOTION_NAME_MAP[key]
    logger.warning("EMOTION MAPPING MISS | '%s' not in EMOTIONS. Fallback to 0.", name)
    return 0


# ---------------------------------------------------------------------------
# Character-position → frame mapping  (unchanged)
# ---------------------------------------------------------------------------

def _build_char_frame_map(aligned_words, clean_script, frame_count):
    n_chars = len(clean_script)
    char_to_frame = np.zeros(n_chars, dtype=np.int32)

    word_timing = [
        (w.word.lower(), w.start_time, w.end_time)
        for w in aligned_words
        if w.start_time is not None and w.end_time is not None
    ]
    if not word_timing:
        return char_to_frame

    script_tokens = []
    i = 0
    while i < n_chars:
        if clean_script[i].isspace():
            i += 1
            continue
        j = i
        while j < n_chars and not clean_script[j].isspace():
            j += 1
        token = clean_script[i:j].lower().strip(".,!?;:\"'()-")
        if token:
            script_tokens.append((i, j, token))
        i = j

    gentle_idx = 0
    last_frame = 0
    for (tok_start, tok_end, token) in script_tokens:
        matched = False
        for lookahead in range(min(3, len(word_timing) - gentle_idx)):
            gidx = gentle_idx + lookahead
            if gidx >= len(word_timing):
                break
            gentle_token = word_timing[gidx][0].strip(".,!?;:\"'()-")
            if gentle_token == token:
                start_t, end_t = word_timing[gidx][1], word_timing[gidx][2]
                gentle_idx = gidx + 1
                n_tok = tok_end - tok_start
                for ci in range(n_tok):
                    frac = ci / max(n_tok - 1, 1)
                    t = start_t + frac * (end_t - start_t)
                    char_to_frame[tok_start + ci] = min(
                        frame_count - 1, max(0, int(math.floor(t * FRAME_RATE)))
                    )
                last_frame = char_to_frame[tok_end - 1]
                matched = True
                break
        if not matched:
            for ci in range(tok_end - tok_start):
                char_to_frame[tok_start + ci] = last_frame

    last = 0
    for idx in range(n_chars):
        if char_to_frame[idx] > 0:
            last = char_to_frame[idx]
        elif last > 0:
            char_to_frame[idx] = last

    first_valid = 0
    for idx in range(n_chars):
        if char_to_frame[idx] > 0:
            first_valid = char_to_frame[idx]
            break
    for idx in range(n_chars):
        if char_to_frame[idx] == 0:
            char_to_frame[idx] = first_valid
        else:
            break

    return char_to_frame


# ---------------------------------------------------------------------------
# Frame helper  — UNIVERSAL -2 anticipation offset  (from v5, unchanged)
# ---------------------------------------------------------------------------

def _frame_onset(timestamp: float) -> int:
    """Convert a phoneme audio-onset timestamp to a frame index.

    Applies the universal 2-frame anticipatory lead, matching the original
    render_frames.py reader:
        frame = max(0, int(timestamp * FPS - 2))

    Applied to EVERY phoneme event without exception.
    """
    return max(0, int(timestamp * FRAME_RATE) - 2)


# ---------------------------------------------------------------------------
# Arc helpers  — v6 slot-corrected
# ---------------------------------------------------------------------------

_OPEN_TRACKS = [
    [[1],       [2],       [2],       [2]],
    [[2, 1],    [1, 2],    [2, 1],    [3, 2]],
    [[1, 2, 1], [1, 3, 2], [2, 3, 1], [2, 3, 2]],
    [[1, 3, 2, 1], [1, 2, 3, 2], [2, 3, 2, 1], [2, 3, 3, 2]],
]

# FIX (Bug A): identity mapping — levels ARE slot numbers in the original system.
# OLD (broken): {0: 4, 2: 1, 4: 0, 5: 0}   ← mapped open→closed and closed→open
# NEW (correct): {0: 0, 2: 2, 4: 4, 5: 5}   ← identity, matching render_frames.py
_LEVEL_TO_SLOT = {0: 0, 2: 2, 4: 4, 5: 5}


def _a_arc(
    frame_len: int,
    start_force: bool,
    end_force: bool,
    prev_shape: str = "m",
    next_shape: str = "m",
) -> list:
    """
    Build the slot sequence for an 'a' (open vowel) arc.

    FIX (Bug A): _LEVEL_TO_SLOT is now identity — levels 0,2,4,5 map to
    slots 0,2,4,5, which correctly address mouth0001, 0003, 0005, 0006.

    FIX (Bug B): Re-added the u-adjacency +1 modifier from the original
    setPhoneme().  When the previous shape is 'u', the first frame is
    bumped +1 (e.g. slot 0 → 1, the y+u-tinge blend).  When the next
    shape is 'u', the last frame is bumped +1.  This produces smooth
    coarticulation at a→u and u→a boundaries.
    """
    if frame_len <= 0:
        return []

    ctx = (2 if start_force else 0) + (1 if end_force else 0)

    if frame_len <= 4:
        choices = _OPEN_TRACKS[frame_len - 1][ctx]
        slots = [_LEVEL_TO_SLOT[(c - 1) * 2] for c in choices]
    else:
        start_size = 2 if start_force else 1
        end_size   = 2 if end_force   else 1
        slots = []
        for i in range(frame_len):
            dist = min(i + start_size, frame_len - 1 - i + end_size)
            if dist >= 3:
                old_level = 4 if (dist % 2 == 1) else 5
            else:
                old_level = (dist - 1) * 2
            slots.append(_LEVEL_TO_SLOT[old_level])

    # FIX (Bug B): u-adjacency modifier — matches original setPhoneme()
    #   if prevPhoneme == 'u': phonemesPerFrame[thisFrame] += 1
    #   if nextPhoneme == 'u': phonemesPerFrame[nextFrame-1] += 1
    if prev_shape == "u" and len(slots) > 0:
        slots[0] = slots[0] + 1
    if next_shape == "u" and len(slots) > 0:
        slots[-1] = slots[-1] + 1

    return slots


def _u_arc(frame_len: int) -> list:
    """
    Build the slot sequence for a 'u' (rounded vowel) arc.

    FIX (Bug C): MOUTH_SHAPE_CODES now has correct slots (o=9, u=10),
    so these references now load mouth0010 and mouth0011 correctly.
    """
    o_slot = MOUTH_SHAPE_CODES["o"]   # 9  → mouth0010 = O-open
    u_slot = MOUTH_SHAPE_CODES["u"]   # 10 → mouth0011 = tight-round sustain
    if frame_len <= 0:
        return []
    if frame_len == 1:
        return [o_slot]
    if frame_len == 2:
        return [o_slot, o_slot]
    return [o_slot] + [u_slot] * (frame_len - 2) + [o_slot]


def _flat_arc(slot: int, frame_len: int) -> list:
    return [slot] * frame_len


def _arc_for_shape(
    shape: str,
    frame_len: int,
    prev_shape: str,
    next_shape: str,
) -> list:
    if frame_len <= 0:
        return []

    if shape == "a":
        sf = prev_shape in _FORCE_OPEN_SET
        ef = next_shape in _FORCE_OPEN_SET
        # Pass prev/next for u-adjacency modifier (Bug B fix)
        return _a_arc(frame_len, sf, ef, prev_shape, next_shape)

    if shape == "u":
        return _u_arc(frame_len)

    if shape == "au":
        mid    = max(1, frame_len // 2)
        a_part = _arc_for_shape("a", mid,             prev_shape, "u")
        u_part = _arc_for_shape("u", frame_len - mid, "a",        next_shape)
        return a_part + u_part

    if shape == "ay":
        mid    = max(1, frame_len // 2)
        a_part = _arc_for_shape("a", mid,             prev_shape, "y")
        # FIX: MOUTH_SHAPE_CODES["y"] is now 0 (mouth0001 = narrow), not 1.
        y_slot = MOUTH_SHAPE_CODES["y"]   # 0
        y_part = _flat_arc(y_slot, frame_len - mid)
        return a_part + y_part

    if shape == "ua":
        mid    = max(1, frame_len // 2)
        u_part = _arc_for_shape("u", mid,             prev_shape, "a")
        a_part = _arc_for_shape("a", frame_len - mid, "u",        next_shape)
        return u_part + a_part

    slot = MOUTH_SHAPE_CODES.get(shape, MOUTH_SHAPE_CODES["m"])
    return _flat_arc(slot, frame_len)


# ---------------------------------------------------------------------------
# Diphthong component lookup
# ---------------------------------------------------------------------------

_DIPHTHONG_SPLIT = {
    "au": ("a", "u"),   # aw/ow: open jaw → rounded
    "ay": ("a", "y"),   # ay/ey/iy: open jaw → narrow spread
    "ua": ("u", "a"),   # oy: rounded → open jaw
}


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class AnimationScheduler:
    """Produces phonemes[], poses[], emotions[] — all of length frame_count."""

    def __init__(self):
        self.frame_count  = 0
        self.pose_history = []

    # ──────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRYPOINT
    # ──────────────────────────────────────────────────────────────────────

    def schedule_frames(
        self,
        aligned_words,
        total_duration,
        clean_script,
        parser_metadata=None,
    ):
        self.frame_count = int(math.ceil(total_duration * FRAME_RATE))

        logger.info(
            "=== SCHEDULER v6 START === Duration=%.2fs Frames=%d FPS=%d",
            total_duration, self.frame_count, FRAME_RATE,
        )

        closed   = MOUTH_SHAPE_CODES["m"]   # 8 → mouth0009
        phonemes = np.full(self.frame_count, closed, dtype=np.int32)
        emotions = self._build_emotion_timeline(parser_metadata, aligned_words, clean_script)
        poses    = self._build_pose_timeline(aligned_words, clean_script, parser_metadata)
        self._build_phoneme_timeline(phonemes, aligned_words, clean_script, parser_metadata)
        self._validate_schedule(phonemes, poses, emotions)
        self._log_summary(phonemes, poses, emotions)
        return phonemes, poses, emotions

    # ──────────────────────────────────────────────────────────────────────
    # POSE TIMELINE  (unchanged from v5)
    # ──────────────────────────────────────────────────────────────────────

    def _build_pose_timeline(
        self, aligned_words, clean_script, parser_metadata
    ) -> np.ndarray:
        poses = np.zeros(self.frame_count, dtype=np.int32)
        change_times = set()

        if aligned_words:
            script_lower = clean_script.lower()
            char_ptr = 0
            for word in aligned_words:
                if word.start_time is None:
                    continue
                wl = word.word.lower().strip(".,!?;:\"'()-")
                try:
                    found    = script_lower.index(wl, char_ptr)
                    char_ptr = found + len(wl)
                    segment  = clean_script[max(0, found - 3): found + len(wl) + 3]
                    for stopper in _SENTENCE_STOPPERS:
                        if stopper in segment:
                            change_times.add(word.start_time)
                            break
                except ValueError:
                    pass

        if parser_metadata and hasattr(parser_metadata, "paragraph_breaks"):
            char_to_frame = _build_char_frame_map(
                aligned_words, clean_script, self.frame_count
            )
            for char_pos in parser_metadata.paragraph_breaks:
                frm = int(char_to_frame[min(char_pos, len(clean_script) - 1)])
                change_times.add(frm / FRAME_RATE)

        sorted_changes = sorted(change_times)
        pose_events    = []
        current_pose   = self._pick_new_pose()
        last_t         = 0.0

        for t in sorted_changes:
            if t <= last_t + POSE_CHANGE_MIN_SECONDS:
                continue
            pose_events.append((last_t, current_pose))
            current_pose = self._pick_new_pose()
            last_t = t

        t = last_t
        while t < (self.frame_count / FRAME_RATE):
            pose_events.append((t, current_pose))
            dur          = random.uniform(POSE_CHANGE_MIN_SECONDS, POSE_CHANGE_MAX_SECONDS)
            t           += dur
            current_pose = self._pick_new_pose()

        for i, (start_t, pid) in enumerate(pose_events):
            start_f = _frame_onset(start_t + 2 / FRAME_RATE)
            end_f   = (
                _frame_onset(pose_events[i + 1][0] + 2 / FRAME_RATE)
                if i + 1 < len(pose_events)
                else self.frame_count
            )
            start_f = max(0, min(start_f, self.frame_count - 1))
            end_f   = max(start_f + 1, min(end_f, self.frame_count))
            poses[start_f:end_f] = pid

        return poses

    # ──────────────────────────────────────────────────────────────────────
    # EMOTION TIMELINE  (unchanged from v5)
    # ──────────────────────────────────────────────────────────────────────

    def _build_emotion_timeline(
        self, parser_metadata, aligned_words, clean_script
    ) -> np.ndarray:
        emotions = np.zeros(self.frame_count, dtype=np.int32)
        if not parser_metadata or not parser_metadata.emotion_events:
            logger.warning("No emotion events — entire timeline uses ID=0.")
            return emotions

        resolved = [
            (ev.position, _emotion_name_to_id(ev.emotion_code))
            for ev in parser_metadata.emotion_events
        ]
        char_to_frame = _build_char_frame_map(
            aligned_words, clean_script, self.frame_count
        )

        seen, deduped = {}, []
        for char_pos, eid in resolved:
            frm = int(char_to_frame[min(char_pos, len(clean_script) - 1)])
            if frm not in seen:
                seen[frm] = eid
                deduped.append((frm, eid))
            else:
                logger.warning(
                    "EMOTION FRAME COLLISION at frame %d — skipping ID=%d", frm, eid
                )

        for i, (start_frm, eid) in enumerate(deduped):
            end_frm = deduped[i + 1][0] if i + 1 < len(deduped) else self.frame_count
            end_frm = min(max(end_frm, start_frm + 1), self.frame_count)
            emotions[start_frm:end_frm] = eid

        logger.info("Emotion IDs present: %s", np.unique(emotions).tolist())
        return emotions

    # ──────────────────────────────────────────────────────────────────────
    # PHONEME TIMELINE  (v5 logic, unchanged except arc calls now pass
    #                    prev/next for u-adjacency fix)
    # ──────────────────────────────────────────────────────────────────────

    def _build_phoneme_timeline(
        self,
        phonemes: np.ndarray,
        aligned_words,
        clean_script: str,
        parser_metadata,
    ) -> None:
        logger.info("Building phoneme timeline (v6)...")

        line_break_char_positions: set[int] = set()
        if parser_metadata and hasattr(parser_metadata, "line_breaks"):
            line_break_char_positions = set(parser_metadata.line_breaks)

        word_end_char: list[int] = []
        script_lower = clean_script.lower()
        char_ptr     = 0
        for word in aligned_words:
            wl = word.word.lower().strip(".,!?;:\"'()-")
            try:
                found    = script_lower.index(wl, char_ptr)
                end_pos  = found + len(wl)
                char_ptr = end_pos
            except ValueError:
                end_pos = char_ptr
            word_end_char.append(end_pos)

        raw_events: list[tuple[str, int]] = []
        prev_abstract = "na"

        for word_idx, word in enumerate(aligned_words):
            if word.start_time is None or word.end_time is None or not word.phones:
                continue

            running = word.start_time

            for phone in word.phones:
                t_start  = running
                running += phone.duration
                t_mid    = t_start + phone.duration * 0.5

                code  = phone.phone.split("_")[0].lower()
                shape = "m" if code == "sil" else PHONEME_MAP.get(code, "m")

                if shape in _DIPHTHONG_SPLIT:
                    first_shape, second_shape = _DIPHTHONG_SPLIT[shape]
                    if first_shape != prev_abstract:
                        raw_events.append((first_shape, _frame_onset(t_start)))
                        prev_abstract = first_shape
                    if second_shape != prev_abstract:
                        raw_events.append((second_shape, _frame_onset(t_mid)))
                        prev_abstract = second_shape
                else:
                    if shape != prev_abstract:
                        raw_events.append((shape, _frame_onset(t_start)))
                        prev_abstract = shape

            # Line-break mouth closing (unchanged from v5)
            if word_idx + 1 < len(aligned_words):
                this_end = word_end_char[word_idx]
                try:
                    next_word    = aligned_words[word_idx + 1]
                    nw_text      = next_word.word.lower().strip(".,!?;:\"'()-")
                    nw_found     = script_lower.index(nw_text, this_end)
                    between_text = clean_script[this_end:nw_found]
                    has_lb       = "\n" in between_text
                except (ValueError, AttributeError):
                    has_lb = False

                if has_lb and prev_abstract in _OPEN_SHAPES_FOR_CLOSE:
                    if word.end_time is not None:
                        raw_events.append(("m", _frame_onset(word.end_time)))
                        prev_abstract = "m"

        if not raw_events:
            return

        raw_events.sort(key=lambda e: e[1])
        deduped: list[tuple[str, int]] = []
        for shape, frm in raw_events:
            if deduped and frm <= deduped[-1][1]:
                frm = deduped[-1][1] + 1
            if frm < self.frame_count:
                deduped.append((shape, frm))

        deduped.append(("m", self.frame_count))
        self._apply_arc_events(phonemes, deduped)

    # ──────────────────────────────────────────────────────────────────────
    # ARC APPLICATION
    # ──────────────────────────────────────────────────────────────────────

    def _apply_arc_events(
        self, phonemes: np.ndarray, events: list
    ) -> None:
        n = len(events)
        for i in range(n - 1):
            shape, frm = events[i]
            next_frm   = events[i + 1][1]
            prev_shape = events[i - 1][0] if i > 0 else "m"
            next_shape = events[i + 1][0]

            frame_len = min(next_frm, self.frame_count) - frm
            if frame_len <= 0:
                continue

            arc        = _arc_for_shape(shape, frame_len, prev_shape, next_shape)
            target_end = min(frm + len(arc), self.frame_count)
            phonemes[frm:target_end] = arc[: target_end - frm]

    # ──────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _pick_new_pose(self) -> int:
        forbidden = set(self.pose_history[-2:])
        choices   = [p for p in range(POSE_COUNT) if p not in forbidden]
        pose      = random.choice(choices) if choices else random.randint(0, POSE_COUNT - 1)
        self.pose_history.append(pose)
        return pose

    def _validate_schedule(self, phonemes, poses, emotions) -> None:
        for name, arr in (
            ("Phoneme", phonemes), ("Pose", poses), ("Emotion", emotions)
        ):
            if len(arr) != self.frame_count:
                raise RuntimeError(
                    f"{name} count mismatch: {len(arr)} vs {self.frame_count}"
                )
        logger.info("Validation OK — %d frames.", self.frame_count)

    def _log_summary(self, phonemes, poses, emotions) -> None:
        logger.info("Emotion IDs used: %s", np.unique(emotions).tolist())
        logger.info("Pose IDs used: %s",    np.unique(poses).tolist())
        u, c = np.unique(phonemes, return_counts=True)
        for slot, count in zip(u, c):
            logger.info("Slot %02d: %d frames", slot, count)