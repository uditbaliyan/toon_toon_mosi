"""
MouthBlender  — professional-grade lip sync post-processor

Sits between the AnimationScheduler (which outputs a flat int32 phonemes[]
array of slot indices) and the FrameRenderer (which composites mouth sprites).

INPUT:  phonemes[]  — raw slot-index array, one value per frame (from scheduler)
OUTPUT: list[BlendState] — one BlendState per frame, consumed by FrameRenderer

Each BlendState carries two sprite slots + a blend weight, plus an optional
micro-drift offset.  The renderer alpha-composites slot_a and slot_b using
weight to produce a position "between" two discrete sprites.

═══════════════════════════════════════════════════════════════════════════════
TECHNIQUE 1 — Cross-frame alpha blending
───────────────────────────────────────────────────────────────────────────────
Every slot transition is spread across BLEND_FRAMES frames.  The outgoing
slot fades out while the incoming slot fades in.  No more teleporting mouths.

    Frame 0:  slot_a=old  slot_b=new  weight=0.0  (100% old)
    Frame 1:  slot_a=old  slot_b=new  weight=0.33
    Frame 2:  slot_a=old  slot_b=new  weight=0.67
    Frame 3:  slot_a=old  slot_b=new  weight=1.0  (100% new)

TECHNIQUE 2 — Easing curves per transition type
───────────────────────────────────────────────────────────────────────────────
The blend weight is not linear — it is passed through a curve chosen by the
TRANSITION TYPE of the specific old→new slot pair:

    EASE_OUT   — opening moves (jaw drops): fast start, slow settle
                 Curve: 1 - (1-t)²   (decelerate to open)
    EASE_IN    — closing moves (jaw rises): slow start, snap shut
                 Curve: t²           (accelerate to closed)
    EASE_INOUT — neutral transitions (consonant↔consonant, vowel↔vowel)
                 Curve: 3t²-2t³      (smooth S-curve)
    SNAP       — plosive consonants (m, b, p): instant hold, no blend
                 Curve: step at 0.5  (hard cut halfway through blend window)

TECHNIQUE 3 — Anticipation frames
───────────────────────────────────────────────────────────────────────────────
For transitions into wide-open vowels (slot 0,4,5 = peak-open shapes),
1 frame BEFORE the transition starts, the incoming slot is pre-blended at
ANTICIPATION_WEIGHT (≈ 0.15).  This mimics the way real mouths pre-open
slightly before a vowel onset, which the human eye reads as natural.

TECHNIQUE 4 — Hold micro-variation
───────────────────────────────────────────────────────────────────────────────
Sustained holds of the same slot for > HOLD_THRESHOLD frames get a small
±1-slot drift applied every DRIFT_PERIOD frames.  The drift is ±1 at weight
DRIFT_WEIGHT (≈ 0.12), so it is subtle — just enough to break the "frozen"
look on long vowels.  The drift alternates direction each period to produce a
gentle oscillation rather than a random walk.

TECHNIQUE 5 — Sub-sprite interpolation
───────────────────────────────────────────────────────────────────────────────
Since the blend weight is a float, the renderer can do a true alpha composite
of two adjacent mouth PNGs.  This gives us N×(N-1)/2 = 55 effective positions
from 11 sprites.  The FrameRenderer's render_frame() already accepts two slot
IDs and a weight; this module produces those values.

The renderer in frame_renderer_v6.py is updated to accept a BlendState instead
of a single mouth_id integer.

═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np


_OPEN_SLOTS  = frozenset({0, 1, 2, 3, 4, 5, 9})
_CLOSE_SLOTS = frozenset({8})
_SNAP_SLOTS  = frozenset({6, 7, 8})
_WIDE_OPEN   = frozenset({4, 5, 9, 10})
_EASE_OUT="ease_out"
_EASE_IN="ease_in"
_EASE_INOUT="ease_inout"
_SNAP_CURVE="snap"

def _easing(t, curve):
    t = max(0.0, min(1.0, t))
    if curve == _EASE_OUT:
        return 1.0-(1.0-t)**2
    if curve == _EASE_IN:
        return t*t
    if curve == _EASE_INOUT:
        return t*t*(3.0-2.0*t)
    if curve == _SNAP_CURVE:
        return 0.0 if t < 0.5 else 1.0
    return t

def _transition_curve(slot_from, slot_to):
    from_open = slot_from in _OPEN_SLOTS
    to_close  = slot_to   in _CLOSE_SLOTS
    to_open   = slot_to   in _OPEN_SLOTS

    # m (closed/silence): snap only when coming from another snap/consonant
    # (e.g. silence gap between words).  When coming FROM an open vowel,
    # ease-in so the jaw closes smoothly rather than teleporting.
    if slot_to == 8:
        return _EASE_IN if from_open else _SNAP_CURVE

    # t and f: always snap in (hard contact points)
    if slot_to in {6, 7}:
        return _EASE_IN   # fast snap, not instant — gives a tiny softness

    # open vowel following a closed/consonant state
    if to_open and not from_open:
        return _EASE_OUT

    # open vowel → open vowel (vowel-to-vowel glide)
    if to_open and from_open:
        return _EASE_INOUT

    return _EASE_INOUT

@dataclass
class BlendState:
    slot_a:int=8
    slot_b:int=8
    weight:float=0.0
    @property
    def is_pure(self):
        return self.slot_a==self.slot_b or abs(self.weight)<0.01

BLEND_FRAMES=4
ANTICIPATION_WEIGHT=0.15
HOLD_THRESHOLD=7
DRIFT_PERIOD=4
DRIFT_MAGNITUDE=1
DRIFT_WEIGHT=0.12

def process(phonemes):
    n=len(phonemes)
    states=[BlendState(slot_a=int(phonemes[i]),slot_b=int(phonemes[i])) for i in range(n)]
    i=0
    while i<n:
        j=i+1
        while j<n and phonemes[j]==phonemes[i]: j+=1
        if j<n:
            sf=int(phonemes[j-1]); st=int(phonemes[j])
            curve=_transition_curve(sf,st)
            anf=j-1
            if st in _WIDE_OPEN and anf>=0 and states[anf].is_pure:
                states[anf]=BlendState(sf,st,ANTICIPATION_WEIGHT)
            bend=min(j+BLEND_FRAMES,n)
            for k in range(j,bend):
                t_raw=(k-j+1)/BLEND_FRAMES
                w=_easing(t_raw,curve)
                ex=states[k]
                if ex.slot_a==sf and ex.slot_b==sf:
                    states[k]=BlendState(sf,st,w)
        i=j
    NO_DRIFT={6,7,8}; i=0; direction=1
    while i<n:
        slot=int(phonemes[i]); j=i+1
        while j<n and phonemes[j]==slot: j+=1
        hold_len=j-i
        if hold_len>HOLD_THRESHOLD and slot not in NO_DRIFT:
            tick=0
            for k in range(i+HOLD_THRESHOLD,j):
                if tick%DRIFT_PERIOD==0:
                    ds=max(0,min(10,slot+direction*DRIFT_MAGNITUDE))
                    direction=-direction
                    if states[k].is_pure:
                        states[k]=BlendState(slot,ds,DRIFT_WEIGHT)
                tick+=1
        i=j
    return states

def blend_mouth_images(a,b,w):
    wa=1.0-w; wb=w
    return np.clip(wa*a.astype(np.float32)+wb*b.astype(np.float32),0,255).astype(np.uint8)




# ─────────────────────────────────────────────────────────────────────────────
# Slot taxonomy  (matches config_fixed.py MOUTH_SHAPE_CODES)
# ─────────────────────────────────────────────────────────────────────────────


def _transition_curve(slot_from: int, slot_to: int) -> str:
    """Choose the easing curve for a slot_from → slot_to transition."""
    to_close  = slot_to   in _CLOSE_SLOTS
    from_open = slot_from in _OPEN_SLOTS
    to_open   = slot_to   in _OPEN_SLOTS
    to_snap   = slot_to   in _SNAP_SLOTS

    if to_snap and slot_to == 8:   # → m (bilabial closure): snap in
        return _SNAP_CURVE
    if to_snap:                    # → t or f: fast snap
        return _EASE_IN
    if to_close and from_open:     # open vowel → closed: ease-in (jaw rises)
        return _EASE_IN
    if to_open and not from_open:  # closed/consonant → open vowel: ease-out
        return _EASE_OUT
    return _EASE_INOUT             # vowel↔vowel, consonant↔consonant: smooth



# ─────────────────────────────────────────────────────────────────────────────
# MouthBlender
# ─────────────────────────────────────────────────────────────────────────────

class MouthBlender:
    """
    Converts a raw slot-index array (from AnimationScheduler) into a
    per-frame list of BlendState objects ready for FrameRenderer.

    Usage
    ─────
        blender  = MouthBlender()
        states   = blender.process(phonemes)   # phonemes is np.ndarray[int32]
        # then in your render loop:
        for frame, state in enumerate(states):
            renderer.render_frame(..., blend_state=state, ...)
    """

    def process(self, phonemes: np.ndarray) -> list[BlendState]:
        """
        Main entry point.  Returns one BlendState per frame.

        Pipeline:
            1. Detect transition boundaries in the raw slot array.
            2. Expand each transition into BLEND_FRAMES of weighted blends
               with the appropriate easing curve (Techniques 1 & 2).
            3. Insert anticipation pre-blend 1 frame before wide-open vowel
               onsets (Technique 3).
            4. Apply micro-drift to sustained holds (Technique 4).
        """
        n = len(phonemes)
        if n == 0:
            return []

        # Step 1: build base BlendState list (one slot, no blending)
        states: list[BlendState] = [BlendState(slot_a=int(phonemes[i]), slot_b=int(phonemes[i])) for i in range(n)]

        # Step 2 & 3: detect transitions, apply blend windows + anticipation
        self._apply_transitions(phonemes, states)

        # Step 4: apply hold micro-variation
        self._apply_hold_drift(phonemes, states)

        return states

    # ─────────────────────────────────────────────────────────────────────
    # Step 2 + 3: transitions
    # ─────────────────────────────────────────────────────────────────────

    def _apply_transitions(
        self, phonemes: np.ndarray, states: list[BlendState]
    ) -> None:
        n = len(phonemes)
        i = 0
        while i < n:
            # Find the next frame where the slot changes
            j = i + 1
            while j < n and phonemes[j] == phonemes[i]:
                j += 1
            # Transition at frame j: phonemes[j-1] → phonemes[j]
            if j < n:
                slot_from = int(phonemes[j - 1])
                slot_to   = int(phonemes[j])
                curve     = _transition_curve(slot_from, slot_to)

                # Technique 3: anticipation frame (1 frame before onset)
                anticipation_frame = j - 1
                if slot_to in _WIDE_OPEN and anticipation_frame >= 0:
                    existing = states[anticipation_frame]
                    # Only apply if frame is currently a pure hold (no ongoing blend)
                    if existing.is_pure:
                        states[anticipation_frame] = BlendState(
                            slot_a=slot_from,
                            slot_b=slot_to,
                            weight=ANTICIPATION_WEIGHT,
                        )

                # Technique 1 + 2: blend window starting at frame j
                blend_end = min(j + BLEND_FRAMES, n)
                for k in range(j, blend_end):
                    t_raw  = (k - j + 1) / BLEND_FRAMES   # 0 < t_raw ≤ 1
                    weight = _easing(t_raw, curve)
                    # Don't overwrite a later transition's blend state
                    existing = states[k]
                    if existing.slot_a == slot_from and existing.slot_b == slot_from:
                        states[k] = BlendState(
                            slot_a=slot_from,
                            slot_b=slot_to,
                            weight=weight,
                        )
                    # If another transition starts mid-blend, leave it alone
                    # (the later transition takes priority).
            i = j

    # ─────────────────────────────────────────────────────────────────────
    # Step 4: hold micro-variation
    # ─────────────────────────────────────────────────────────────────────

    def _apply_hold_drift(
        self, phonemes: np.ndarray, states: list[BlendState]
    ) -> None:
        """
        For sustained holds of the same slot, add a gentle micro-drift every
        DRIFT_PERIOD frames so the mouth doesn't look frozen.

        The drift alternates ±DRIFT_MAGNITUDE to produce a slow oscillation.
        Skip slots that shouldn't drift: m/closed (8) looks fine frozen,
        and consonant snaps (t=6, f=7) are typically too short to need it.
        """
        NO_DRIFT_SLOTS = {6, 7, 8}   # t, f, m — contacts/closures, don't drift
        MAX_SLOT = 10

        n = len(phonemes)
        i = 0
        direction = 1   # alternates each drift tick

        while i < n:
            slot = int(phonemes[i])
            # Find end of hold
            j = i + 1
            while j < n and phonemes[j] == slot:
                j += 1
            hold_len = j - i

            if hold_len > HOLD_THRESHOLD and slot not in NO_DRIFT_SLOTS:
                # Apply drift ticks starting after HOLD_THRESHOLD frames
                tick = 0
                for k in range(i + HOLD_THRESHOLD, j):
                    if tick % DRIFT_PERIOD == 0:
                        drift_slot = slot + direction * DRIFT_MAGNITUDE
                        drift_slot = max(0, min(MAX_SLOT, drift_slot))
                        direction  = -direction   # flip for next tick
                        # Only apply to frames that are currently pure holds
                        if states[k].is_pure:
                            states[k] = BlendState(
                                slot_a=slot,
                                slot_b=drift_slot,
                                weight=DRIFT_WEIGHT,
                            )
                    tick += 1
            i = j


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: blend_mouth_images()  — called by FrameRenderer
# ─────────────────────────────────────────────────────────────────────────────

def blend_mouth_images(
    img_a: "np.ndarray",
    img_b: "np.ndarray",
    weight: float,
) -> "np.ndarray":
    """
    Alpha-composite two mouth BGRA images using a scalar blend weight.

    weight=0.0 → 100% img_a
    weight=1.0 → 100% img_b
    Intermediate values produce a true alpha-weighted composite.

    Both images must be the same shape (H, W, 4).  If they differ in size,
    img_b is resized to match img_a before blending.

    This is Technique 5: sub-sprite interpolation.  By blending adjacent
    sprites the renderer achieves positions between discrete mouth shapes.
    """
    import cv2

    if img_b.shape != img_a.shape:
        img_b = cv2.resize(
            img_b,
            (img_a.shape[1], img_a.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        )

    w  = float(max(0.0, min(1.0, weight)))
    wa = 1.0 - w
    wb = w

    # Float composite on all 4 channels (including alpha)
    blended = (wa * img_a.astype(np.float32) + wb * img_b.astype(np.float32))
    return np.clip(blended, 0, 255).astype(np.uint8)
